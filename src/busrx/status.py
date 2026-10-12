"""수신기 현황 조립 — 관리 페이지(`web.py`)와 텔레그램 명령(`bot.py`)이 같이 쓴다."""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import time
import urllib.request
from pathlib import Path

from src.bus import envelope as E

from .claude import KST, pct

HB_LOST_SEC = 120


def read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def age_of(ts: str, now: float) -> float | None:
    try:
        return now - dt.datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc).timestamp()
    except Exception:
        return None


def usage_view(rx, now: float) -> dict | None:
    u = rx.usage_now()
    return dict(u, age=int(now - u.get("t", now))) if u else None


def build_status(rx, cfg, now: float) -> dict:
    bus = cfg.bus_dir
    pub = read_json(bus / "hb" / "publisher.json") or {}
    age = age_of(pub.get("ts", ""), now)
    runner = read_json(cfg.runner_dir / "_local" / "ops" / "runner.json") or {}
    healthy = None
    if runner.get("port"):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{runner['port']}/healthz-local", timeout=1.5) as r:
                healthy = json.loads(r.read().decode()).get("ok") is True
        except Exception:
            healthy = False
    today = rx._today()
    head = subprocess.run(["git", "-C", str(cfg.repo), "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    return dict(
        now=E.iso(now), stage=cfg.stage, models={"analysis": cfg.model_analysis, "code": cfg.model_code},
        rx_paused=rx.paused(), apply_local=cfg.apply_local, apply_branch=cfg.apply_branch, head=head,
        publisher={"alive": age is not None and age <= HB_LOST_SEC, "age": None if age is None else int(age),
                   "level": pub.get("level"), "paused": pub.get("paused"), "counters": pub.get("counters"), "pid": pub.get("pid")},
        receiver={"pid": os.getpid(), "calls_today": rx.state["calls"].get(today, 0), "daily_cap": cfg.daily_cap,
                  "fixes_today": rx.state.get("fixes", {}).get(today, 0), "fix_cap": cfg.fix_daily_cap},
        queue={k: rx.spool.count(f"err/{k}") for k in ("inbox", "processing", "done", "dead")},
        runner={"pid": runner.get("pid"), "port": runner.get("port"), "healthy": healthy},
        lost_alerted=rx.state.get("lost_alerted", False), usage=usage_view(rx, now), policy=rx.policy.all(),
        mode=rx.policy.mode(), proposals_pending=rx.proposals.pending_count())


def _kst(epoch, with_date: bool) -> str:
    try:
        d = dt.datetime.fromtimestamp(int(epoch), KST)
        return d.strftime("%m-%d %H:%M" if with_date else "%H:%M")
    except Exception:
        return "?"


def usage_text(u: dict | None) -> list[str]:
    """텔레그램용 사용량 줄(세션/주간)."""
    if not u:
        return ["사용량: 아직 측정값 없음 (/usage 로 조회)"]
    out = []
    if u.get("five") is not None:
        out.append(f"세션(5시간): {pct(u['five'])} 사용 · 남음 {pct(1 - u['five'])} · 초기화 {_kst(u['reset5'], False)} KST")
    if u.get("seven") is not None:
        out.append(f"주간(7일): {pct(u['seven'])} 사용 · 남음 {pct(1 - u['seven'])} · 초기화 {_kst(u['reset7'], True)} KST")
    mins = int(u.get("age", 0)) // 60
    out.append(f"(측정 {mins}분 전)" if mins else "(방금 측정)")
    return out


def policy_line(pol: dict | None) -> str:
    if not pol:
        return ""
    from .autofix import PRESETS
    name = {"off": "끔", "analyze": "분석", "fix": "수정"}
    parts = []
    for sev in ("CRITICAL", "ERROR", "WARN"):
        p = pol.get(sev)
        if p:
            parts.append(f"{sev} {name[p['action']]}" + (f"({PRESETS[p['preset']]['name'].split('(')[0]})" if p["action"] == "fix" else ""))
    return "정책: " + " · ".join(parts)


def status_text(s: dict) -> str:
    p, r = s["publisher"], s["receiver"]
    run = s["runner"]
    lines = [
        f"🤖 자동제어 현황 · {s['stage']}단계 · 모드 {({'auto': '자동', 'semi': '반자동', 'off': '끔'}).get(s.get('mode'), '?')}"
        + (f" · 승인 대기 {s['proposals_pending']}건" if s.get("proposals_pending") else ""),
        f"수신기 분석: {'⏸ 정지됨' if s['rx_paused'] else '▶ 동작 중'}",
        f"발신기: {'정상' if p['alive'] else '⚠️ 신호 없음'}" + (f" · 레벨 {p['level']}" if p.get("level") else "")
        + (" · 발신 정지" if p.get("paused") else "") + (f" · {p['age']}초 전" if p.get("age") is not None else ""),
        f"러너: {'정상' if run['healthy'] else ('⚠️ 응답 없음' if run['healthy'] is False else '확인 불가')}"
        + (f" (pid {run['pid']})" if run.get("pid") else ""),
        f"오늘 분석 {r['calls_today']}/{r['daily_cap']} · 수정 시도 {r['fixes_today']}/{r['fix_cap']} · inbox {s['queue']['inbox']}",
        f"로컬 적용 {'켜짐' if s['apply_local'] else '꺼짐'} · 브랜치 {s['apply_branch']} · HEAD {s['head']}",
        policy_line(s.get("policy")), "", *usage_text(s["usage"])]
    return "\n".join(lines)
