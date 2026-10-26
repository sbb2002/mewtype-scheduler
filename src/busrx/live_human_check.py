"""'사람 조치 필요' 판정 실전 시험 — 진짜 claude(Sonnet 분석 · 명세, Haiku 구현)로 외부 API 장애별로 어떻게 반응하는지 본다.

    python -m src.busrx.live_human_check [시나리오 id ...]      # 생략하면 전부

격리: 저장소를 임시 폴더로 복제해 거기서만 수정 · 커밋한다(실제 저장소 · 러너 · 운영자 수신기에는 손대지 않는다).
재시작은 하지 않는다. 구독 사용량을 쓴다(시나리오당 분석 1회, 수정 대상이면 명세 · 구현 · 검증 · 검토까지).
결과는 표로 출력하고 `<임시폴더>/result.json` 에 남긴다.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from src.bus import envelope as E

from .receiver import ROOT, Config, Receiver, signature

SCENARIOS = {
    # id: (logger, 심각도, 메시지, 기대: needs_human)
    "groq401": ("src.backend.llm", "ERROR",
                'Groq 401: {"error":{"message":"Invalid API Key","type":"invalid_request_error","code":"invalid_api_key"}}', True),
    "groq402": ("src.backend.llm", "ERROR",
                'Groq 402: {"error":{"message":"Payment required: the free tier has ended. Add a payment method to continue.","code":"payment_required"}}', True),
    "yt403": ("src.collector.youtube", "ERROR",
              "videos.list 403: quotaExceeded — The request cannot be completed because you have exceeded your quota.", True),
    "github401": ("src.backend.gh_store", "ERROR", "GitHub PUT preview.json 401: Bad credentials (token expired or revoked)", True),
    "telegram401": ("src.backend.telegram_app", "ERROR", "Telegram sendMessage 401 Unauthorized: bot token revoked", True),
    # 대조군 — 코드가 원인인 것(수정 대상)과 일시 장애(사람 조치도 수정도 아님)
    "codebug": ("src.backend.fault_lab", "ERROR",
                "clamp(15, 0, 10) 가 0 을 반환 — 상한을 넘으면 hi(10)를 돌려줘야 하는데 lo 를 돌려준다 (src/backend/fault_lab.py clamp)", False),
    "transient503": ("src.backend.llm", "WARN", "Groq 503: 백오프 소진 (3/3) — 단발성, 다음 호출은 정상", False),
}


class _TG:
    enabled = True

    def __init__(self):
        self.msgs = []

    def send(self, text):
        self.msgs.append(text)
        return True

    def send_file(self, name, content, caption=""):
        self.msgs.append(f"[파일 {name}] {caption}")
        return True


def main() -> int:
    ids = sys.argv[1:] or list(SCENARIOS)
    tmp = Path(tempfile.mkdtemp(prefix="mewlive_"))
    repo = tmp / "repo"
    subprocess.run(["git", "clone", "--local", "--no-hardlinks", "-q", str(ROOT), str(repo)], check=True)
    # 시험 중인 작업본(미커밋 포함)을 복제본에 그대로 반영 — 분석기가 읽는 코드가 현재 코드와 같도록
    br = subprocess.run(["git", "-C", str(ROOT), "branch", "--show-current"], capture_output=True, text=True).stdout.strip() or "test-fullauto-hotfix"
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-B", br], check=True)
    cfg = Config(bus_dir=tmp / "bus", repo=repo, stage=2, apply_local=True, apply_branch=br, runner_dir=tmp / "runner",
                 batch_wait_sec=0, cooldown_error=0, cooldown_critical=0)
    (tmp / "runner").mkdir(exist_ok=True)
    tg = _TG()
    rx = Receiver(cfg, tg)
    rx._restart = lambda c: (True, "시험 — 재시작하지 않음")  # 러너를 건드리지 않는다
    rx.policy.save({"WARN": {"action": "fix"}})            # 대조군 일시 장애도 수정 경로까지 가도록 WARN 도 fix 로(시험용)
    rows = []
    for sid in ids:
        logger, sev, msg, expect = SCENARIOS[sid]
        env = E.build_err(kind="log", severity=sev, message=msg, source={"env": "local", "service": "runner", "commit": "live"}, logger=logger)
        sig = signature(env)
        n_msgs, t0 = len(tg.msgs), time.time()
        rx.spool.put("err/inbox", f"{env['ts'].replace('-', '').replace(':', '')}_{env['id']}", env)
        rx.step()
        run = None
        for p in sorted((cfg.rx / "runs").glob("*.json"), reverse=True):
            d = json.loads(p.read_text(encoding="utf-8"))
            if d.get("sig") == sig:
                run = d
                break
        a = (run or {}).get("analysis") or {}
        names = [s["name"] for s in (run or {}).get("steps", [])]
        started_fix = any(n.startswith(("명세서", "구현", "검증", "독립")) for n in names)
        rows.append({"id": sid, "expect_needs_human": expect, "verdict": a.get("verdict"), "needs_human": bool(a.get("needs_human")),
                     "human_action": a.get("human_action", ""), "summary": a.get("summary", ""), "fix_started": started_fix,
                     "fix_status": (run or {}).get("fix_status"), "files": [f["path"] for f in (run or {}).get("files", [])],
                     "flagged": bool(rx.human_flag(sig)), "tg_human_msg": any("사람 조치 필요" in m for m in tg.msgs[n_msgs:]),
                     "sec": round(time.time() - t0)})
        print(json.dumps(rows[-1], ensure_ascii=False), flush=True)
    (tmp / "result.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n결과 파일:", tmp / "result.json")
    print("| 시나리오 | 기대 | 판정 | needs_human | 수정 단계 시작 | 표시 | 알림 |")
    for r in rows:
        print(f"| {r['id']} | {'사람' if r['expect_needs_human'] else '코드/일시'} | {r['verdict']} | {r['needs_human']} | {r['fix_started']} ({r['fix_status']}) | {r['flagged']} | {r['tg_human_msg']} |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
