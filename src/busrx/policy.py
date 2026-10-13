"""에러 레벨별 자동 대응 정책 — 심각도마다 기록 · 분석 · 수정 파이프라인 시작 여부와 프리셋 · 쿨다운을 정한다.

저장: `<버스>/rx/policy.json` (관리 페이지에서 수정 → 수신기가 다음 에러부터 바로 반영, 재시작 불필요). 변경 이력: `rx/policy_history.jsonl`.
기본값은 운영자 정의(2026-10-12)를 따른다:
  CRITICAL = 즉각 패치 + 최소 동작 검증(긴급 프리셋)  /  ERROR = 패치 + 충분한 검증(표준 프리셋)
  WARN = 로그만  /  INFO · DEBUG = 반응 없음
모든 심각도에서 "수정까지"를 고를 수 있다(2026-10-13 운영자 결정 — 이전에는 WARN 이하 수정 불가였음). 수정 일일 상한 · 가드 · 보호확인은 심각도와 무관하게 그대로 적용된다.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from src.bus import envelope as E

from . import pipelines

SEVERITIES = E.SEVERITIES  # CRITICAL ERROR WARN INFO DEBUG
ACTIONS = {"off": "끔(기록만)", "analyze": "분석만", "fix": "수정까지"}
COOLDOWN_MAX = 7 * 86400
# 동작 모드(전체): auto = 전부 자동 패치(기본) / semi = 분석 후 패치 계획안을 만들어 사람의 승인 · 반려(재계획) · 거절을 기다림 / off = 자동제어 동작 안 함(기록만)
MODES = {"auto": "자동", "semi": "반자동", "off": "끔"}


def defaults(cfg) -> dict:
    d = {s: {"record": True, "action": "off", "preset": "standard", "cooldown_sec": 3600} for s in SEVERITIES}
    d["CRITICAL"] = {"record": True, "action": "fix", "preset": "urgent", "cooldown_sec": cfg.cooldown_critical}
    d["ERROR"] = {"record": True, "action": "fix", "preset": "standard", "cooldown_sec": cfg.cooldown_error}
    return d


def validate(raw: dict, base: dict, presets=None) -> tuple[dict, list[str]]:
    """raw(사용자 입력)를 base 위에 덮어 검증. (정리된 전체 정책, 오류 목록)"""
    out = {s: dict(v) for s, v in base.items()}
    errs: list[str] = []
    presets = list(presets) if presets is not None else list(pipelines.BUILTIN)
    if not isinstance(raw, dict):
        return out, ["정책이 객체가 아님"]
    for sev, row in raw.items():
        if sev not in SEVERITIES:
            errs.append(f"알 수 없는 심각도 {sev!r}")
            continue
        if not isinstance(row, dict):
            errs.append(f"{sev}: 값이 객체가 아님")
            continue
        cur = out[sev]
        if "record" in row:
            if not isinstance(row["record"], bool):
                errs.append(f"{sev}: record 는 true/false")
            else:
                cur["record"] = row["record"]
        if "action" in row:
            if row["action"] not in ACTIONS:
                errs.append(f"{sev}: action 은 {list(ACTIONS)} 중 하나")
            else:
                cur["action"] = row["action"]
        if "preset" in row:
            if row["preset"] not in presets:
                errs.append(f"{sev}: preset 은 {presets} 중 하나")
            else:
                cur["preset"] = row["preset"]
        if "cooldown_sec" in row:
            c = row["cooldown_sec"]
            if isinstance(c, bool) or not isinstance(c, int) or not 0 <= c <= COOLDOWN_MAX:
                errs.append(f"{sev}: cooldown_sec 는 0~{COOLDOWN_MAX} 정수")
            else:
                cur["cooldown_sec"] = c
    return out, errs


class Policy:
    def __init__(self, path: Path, cfg):
        self.path, self.cfg = path, cfg
        self._cache: dict | None = None
        self._mtime = -1.0
        self._mode = "auto"

    def mode(self) -> str:
        self.all()
        return self._mode

    def set_mode(self, mode: str, who: str = "dashboard") -> tuple[str, list[str]]:
        if mode not in MODES:
            return self.mode(), [f"mode 는 {list(MODES)} 중 하나"]
        old = self.mode()
        levels = self.all()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"levels": levels, "mode": mode, "saved_at": E.iso(time.time())}, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
        self._cache = None
        if old != mode:
            with (self.path.parent / "policy_history.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": E.iso(time.time()), "by": who, "mode": {"from": old, "to": mode}}, ensure_ascii=False) + "\n")
        return self.mode(), []

    def all(self) -> dict:
        try:
            m0 = self.path.stat().st_mtime
        except FileNotFoundError:
            m0 = -2.0
        try:  # 사용자 정의 파이프라인이 바뀌면(삭제 · 초기화) 정책이 가리키는 id 를 다시 검증해야 한다
            m1 = (self.cfg.rx / "pipelines.json").stat().st_mtime
        except FileNotFoundError:
            m1 = -2.0
        m = (m0, m1)
        if self._cache is None or m != self._mtime:
            base = defaults(self.cfg)
            data = None
            if m0 >= 0:
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                except Exception:
                    data = None
            md = data.get("mode") if isinstance(data, dict) else None
            self._mode = md if md in MODES else "auto"
            pol, errs = validate((data or {}).get("levels", {}) if isinstance(data, dict) else {}, base, pipelines.all_pipelines(self.cfg))
            if errs:  # 손상 · 부분 오류가 있으면 오류 항목만 기본값 유지(validate 가 걸러냄)
                pass
            self._cache, self._mtime = pol, m
        return {s: dict(v) for s, v in self._cache.items()}

    def get(self, sev: str) -> dict:
        return self.all().get(sev) or defaults(self.cfg)["DEBUG"]

    def save(self, raw: dict, who: str = "dashboard") -> tuple[dict, list[str]]:
        new, errs = validate(raw, self.all(), pipelines.all_pipelines(self.cfg))
        if errs:
            return self.all(), errs
        old = self.all()
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"levels": new, "mode": self.mode(), "saved_at": E.iso(time.time())}, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)
        changed = {s: {"from": old[s], "to": new[s]} for s in new if new[s] != old[s]}
        if changed:
            with (self.path.parent / "policy_history.jsonl").open("a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": E.iso(time.time()), "by": who, "changed": changed}, ensure_ascii=False) + "\n")
        self._cache = None
        return self.all(), []

    def reset(self, who: str = "dashboard") -> dict:
        self.path.unlink(missing_ok=True)
        self._cache = None
        with (self.path.parent / "policy_history.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": E.iso(time.time()), "by": who, "reset": True}, ensure_ascii=False) + "\n")
        return self.all()
