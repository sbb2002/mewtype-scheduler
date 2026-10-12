"""반자동 모드의 패치 계획안 저장소 — 에러 요약 + 패치 계획(여러 판) + 사용자의 결정 이력.

계획안 1건 = `rx/proposals/<id>.json` + 계획 파일 `rx/proposals/<id>/plan_rev<N>.md`. 상태:
  pending(승인 대기) → approved→running(실행 중) → done / failed
  pending → replanning(반려 후 재계획 중) → pending(새 판)  /  failed(재계획 실패)
  pending → declined(거절 — 아무것도 하지 않음)
  pending → approved→running → held(파이프라인은 통과했으나 적용 보류 — 미커밋 변경과 겹침 등, 수정 브랜치는 보존)
  running · replanning 중에 수신기가 꺼지면 다음 기동 때 interrupted 로 표시
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from src.bus import envelope as E

PENDING_LIKE = ("pending", "replanning", "running")
MAX_REPLANS = 5


class Proposals:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def _p(self, pid: str) -> Path:
        return self.root / f"{pid}.json"

    def get(self, pid: str) -> dict | None:
        try:
            return json.loads(self._p(pid).read_text(encoding="utf-8"))
        except Exception:
            return None

    def _save(self, prop: dict) -> None:
        prop["updated"] = E.iso(time.time())
        tmp = self._p(prop["id"]).with_suffix(".tmp")
        tmp.write_text(json.dumps(prop, ensure_ascii=False, indent=1), encoding="utf-8")
        for i in range(6):
            try:
                os.replace(tmp, self._p(prop["id"]))
                return
            except PermissionError:
                time.sleep(0.05 * (i + 1))
        os.replace(tmp, self._p(prop["id"]))

    def plan_file(self, pid: str, rev: int) -> Path:
        d = self.root / pid
        d.mkdir(parents=True, exist_ok=True)
        return d / f"plan_rev{rev}.md"

    def create(self, *, sig: str, severity: str, base: str, preset: str, error: dict, analysis: dict, plan: dict) -> dict:
        pid = E.new_id()
        prop = {"id": pid, "sig": sig, "severity": severity, "status": "pending", "created": E.iso(time.time()), "base": base,
                "preset": preset, "error": error, "analysis": analysis, "plans": [], "decisions": [], "result": None}
        self._add_plan(prop, plan, feedback="")
        with self._lock:
            self._save(prop)
        return prop

    def _add_plan(self, prop: dict, plan: dict, feedback: str) -> dict:
        rev = len(prop["plans"]) + 1
        entry = {"rev": rev, "ts": E.iso(time.time()), "title": plan["title"], "change_plan": plan["change_plan"], "test_plan": plan["test_plan"],
                 "risk": plan["risk"], "feedback": feedback, "file": f"plan_rev{rev}.md"}
        self.plan_file(prop["id"], rev).write_text(plan["spec_md"], encoding="utf-8")
        prop["plans"].append(entry)
        return entry

    def add_revision(self, pid: str, plan: dict, feedback: str) -> dict | None:
        with self._lock:
            prop = self.get(pid)
            if not prop:
                return None
            self._add_plan(prop, plan, feedback)
            prop["status"] = "pending"
            self._save(prop)
            return prop

    def update(self, pid: str, **fields) -> dict | None:
        with self._lock:
            prop = self.get(pid)
            if not prop:
                return None
            prop.update(fields)
            self._save(prop)
            return prop

    def begin(self, pid: str, expect: tuple, action: str, by: str, note: str = "", status: str | None = None, **fields):
        """상태가 expect 안에 있을 때만 결정을 기록하고 상태를 바꾼다(동시 클릭 방어). (계획안 | None, 현재 상태)"""
        with self._lock:
            prop = self.get(pid)
            if not prop:
                return None, None
            if prop["status"] not in expect:
                return None, prop["status"]
            prop["decisions"].append({"ts": E.iso(time.time()), "action": action, "by": by, "note": note[:500]})
            if status:
                prop["status"] = status
            prop.update(fields)
            self._save(prop)
            return prop, status or prop["status"]

    def decide(self, pid: str, action: str, by: str, note: str = "", **fields) -> dict | None:
        with self._lock:
            prop = self.get(pid)
            if not prop:
                return None
            prop["decisions"].append({"ts": E.iso(time.time()), "action": action, "by": by, "note": note[:500]})
            prop.update(fields)
            self._save(prop)
            return prop

    def list(self, limit: int = 60) -> list[dict]:
        out = []
        for p in sorted(self.root.glob("*.json"), reverse=True)[:limit]:
            try:
                out.append(json.loads(p.read_text(encoding="utf-8")))
            except Exception:
                pass
        return out

    def pending_count(self) -> int:
        return sum(1 for p in self.list(200) if p.get("status") == "pending")

    def recover(self) -> int:
        """수신기가 처리 중에 꺼졌던 계획안(running · replanning)을 interrupted 로 표시. 개수."""
        n = 0
        for p in self.list(500):
            if p.get("status") in ("running", "replanning"):
                self.decide(p["id"], "interrupted", "receiver", "수신기가 처리 중에 종료됨", status="interrupted")
                n += 1
        return n

    def plan_text(self, pid: str, rev: int) -> str | None:
        try:
            return self.plan_file(pid, rev).read_text(encoding="utf-8")
        except Exception:
            return None
