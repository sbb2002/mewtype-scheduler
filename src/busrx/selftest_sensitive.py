"""민감 경로 · 사람 요청 · 데이터 이전 self-test (2026-10-27 — 자동 모드는 사람 개입 최소화, 혼자 못 하는 것만 사람에게).

임시 git 저장소 + 가짜 claude(스텁) + 가짜 텔레그램 · 가짜 재시작 (네트워크 · 모델 호출 없음).

    python -m src.busrx.selftest_sensitive
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import guard, testver
from .autofix import AutoFix
from .claude import clean_env, model_label
from .receiver import RESULT_SCHEMA, SYSTEM_RULES, Config, Receiver, git_head
from .restart import runner_args

STUB = r'''
import json, os, re, sys
prompt = sys.stdin.buffer.read().decode("utf-8", "replace")
argv = sys.argv[1:]
purpose = (re.search(r"\[\[PURPOSE:(\w+)\]\]", prompt) or [None, "?"])[1]
def arg(name):
    return argv[argv.index(name) + 1] if name in argv else ""
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"purpose": purpose, "model": arg("--model"), "sensitive_rules": "땜질 금지" in prompt}) + "\n")
mode = os.environ.get("STUB_MODE", "")
def out(d):
    print(json.dumps({"structured_output": d, "total_cost_usd": 0.01, "is_error": False, "result": ""}))
STORE = os.path.join("src", "backend", "gh_store.py")
STORE_GOOD = "def read():\n    return 'fixed'\n\nif __name__ == \"__main__\":\n    assert read() == 'fixed'\n    print('ok')\n"
MIG = ("import argparse, json, pathlib, sys\n"
       "ap = argparse.ArgumentParser(); ap.add_argument('--data'); ap.add_argument('--ops'); a = ap.parse_args()\n"
       "d = pathlib.Path(a.data)\n"
       "FAIL\n"
       "doc = json.loads((d / 'list.json').read_text(encoding='utf-8'))\n"
       "items = doc.get('items', doc.get('rows', []))\n"
       "(d / 'list.json').write_text(json.dumps({'rows': items}), encoding='utf-8')\n"
       "got = len(json.loads((d / 'list.json').read_text(encoding='utf-8'))['rows'])\n"
       "print('converted', got); sys.exit(0 if got == len(items) else 1)\n")
if purpose == "analysis":
    out({"verdict": "confirmed", "summary": "저장소 읽기 실패", "cause": "형식 불일치", "evidence": [], "proposed_action": "형식 변환", "needs_human": False})
elif purpose in ("spec", "replan"):
    if mode == "spec_human":
        out({"fixable": False, "needs_human": True, "why_not": "새 키 필요",
             "human_need": "새 API 키가 필요합니다. " + "공급자 대시보드에서 발급 · 등록 절차 설명 " * 20,
             "title": "번역 공급자 키 필요", "change_plan": [], "test_plan": "", "risk": ""})
    else:
        mig = mode.startswith("mig")
        out({"fixable": True, "needs_human": False, "human_need": "", "why_not": "",
             "title": "목록 형식 변환" if mig else "저장소 읽기 수정",
             "change_plan": [{"file": "src/backend/gh_store.py", "change": "읽기 수정"}] + ([{"file": "scripts/mig.py", "change": "이전"}] if mig else []),
             "test_plan": "self-test", "risk": "낮음", "auto_decisions": ["재시도 3회 — 기존 관례"] if mig else [],
             **({"migration": {"script": "scripts/mig.py", "purpose": "list.json 의 items 를 rows 로"}} if mig else {})})
elif purpose in ("implement", "revise"):
    if mode == "newkey":
        open(STORE, "w", encoding="utf-8").write("import os\nKEY = os.environ.get('NEW_PROVIDER_KEY')\n" + STORE_GOOD)
    else:
        open(STORE, "w", encoding="utf-8").write(STORE_GOOD)
        os.makedirs("docs", exist_ok=True)
        open(os.path.join("docs", "SPEC.md"), "a", encoding="utf-8").write("\n- 목록 계약\n")
        if mode.startswith("mig"):
            os.makedirs("scripts", exist_ok=True)
            fail = {"mig_ok": "pass", "mig_fail_real": "sys.exit(7) if 'data_try' not in a.data else None"}[mode]
            open(os.path.join("scripts", "mig.py"), "w", encoding="utf-8").write(MIG.replace("FAIL", fail))
    print(json.dumps({"result": "수정 완료", "total_cost_usd": 0.02, "is_error": False}))
elif purpose == "verify":
    out({"approve": True, "issues": [], "summary": "명세서와 일치"})
elif purpose == "review":
    out({"approve": True, "concerns": [], "touches_prod_resources": False, "summary": "독립 검토 완료"})
else:
    sys.exit(3)
'''

STORE_OLD = "def read():\n    return None\n\nif __name__ == \"__main__\":\n    print('ok')\n"


class FakeTG:
    enabled = True

    def __init__(self):
        self.msgs, self.files = [], []

    def send(self, text):
        self.msgs.append(text)
        return True

    def send_file(self, name, content, caption=""):
        self.files.append((name, content, caption))
        return True


def sh(repo: Path, *a: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, (a, r.stderr)
    return r.stdout.strip()


def main() -> int:
    def check(c, m):
        assert c, m
        print("OK ", m)

    # ── 가드: 절대 금지 · 민감 경로 ──
    check(guard.path_violations(["src/backend/gh_store.py", "docs/SPEC.md", "scripts/m.py"]) ==
          ["금지 경로 수정: src/backend/gh_store.py", "금지 경로 수정: docs/SPEC.md", "금지 경로 수정: scripts/m.py"], "가드: 민감 경로는 기본 금지")
    check(guard.path_violations(["src/backend/gh_store.py", "docs/SPEC.md", "scripts/m.py", "src/backend/x.py"], sensitive_ok=True) == [],
          "가드: 민감 경로 허용 시 저장 계층 · docs/ · scripts/ 통과")
    check(guard.path_violations(["src/busrx/a.py", "src/bus/b.py", "src/frontend/i.html", "config/c.json", "deploy/d.sh"], sensitive_ok=True) ==
          ["금지 경로 수정: src/busrx/a.py", "금지 경로 수정: src/bus/b.py", "허용 범위 밖 경로 수정: src/frontend/i.html",
           "허용 범위 밖 경로 수정: config/c.json", "허용 범위 밖 경로 수정: deploy/d.sh"], "가드: 자기 자신 · 프론트 · 설정 · 배포는 민감 허용이어도 위반")
    check(guard.sensitive_paths(["src/backend/gh_store.py", "src/backend/x.py", "docs/SPEC.md"]) == ["src/backend/gh_store.py", "docs/SPEC.md"],
          "가드: 민감 경로 목록 추출")

    # ── claude 서브프로세스 환경 · 모델 표기 · 분석 규칙 ──
    saved = dict(os.environ)
    os.environ.update({"CLAUDE_EFFORT": "high", "CLAUDE_CODE_SESSION_ID": "x", "CLAUDECODE": "1", "CLAUDE_CONFIG_DIR": "/c", "ANTHROPIC_BASE_URL": "u"})
    try:
        ce = clean_env()
    finally:
        os.environ.clear()
        os.environ.update(saved)
    check(not any(k in ce for k in ("CLAUDE_EFFORT", "CLAUDE_CODE_SESSION_ID", "CLAUDECODE")) and ce.get("CLAUDE_CONFIG_DIR") == "/c"
          and ce.get("ANTHROPIC_BASE_URL") == "u", "claude 환경: 세션 변수(CLAUDE_EFFORT 등)는 빼고 CLAUDE_CONFIG_DIR · ANTHROPIC_* 만")
    check(runner_args(r"C:\py\python.exe -m src.backend.local_runner --env .env.local --no-scheduler --no-telegram")
          == ["--env", ".env.local", "--no-scheduler", "--no-telegram"] and runner_args("") == [], "러너 재시작: 원래 실행 인자 유지")
    check(model_label("claude-opus-5-5") == "Opus" and model_label("claude-haiku-5-5") == "Haiku" and model_label("x") == "x", "모델 표기")
    check({"hypothesis", "how_to_confirm"} <= set(RESULT_SCHEMA["properties"]) and "how_to_confirm" in SYSTEM_RULES
          and "혼자 진행할 수 없는 것" in SYSTEM_RULES, "분석 규칙: 유력 가설 · 확인 방법 칸, 사람 조치는 혼자 못 하는 것만")

    # ── 임시 저장소 ──
    tmp = Path(tempfile.mkdtemp(prefix="mewsens_"))
    repo, bus, dd = tmp / "repo", tmp / "bus", tmp / "testdata"
    (repo / "src" / "backend").mkdir(parents=True)
    for d in ("src", "src/backend"):
        (repo / d / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "backend" / "gh_store.py").write_text(STORE_OLD, encoding="utf-8")
    (repo / ".env.local").write_text("TELEGRAM_BOT_TOKEN=local-only-token-value\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".env.local\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "SPEC.md").write_text("# SPEC\n", encoding="utf-8")
    (repo / "docs" / "VERSION_vT.md").write_text("# t\n" + testver.MARK + "\n\n## vT1.0.0 — 기준선\n", encoding="utf-8")
    sh(repo, "init", "-q", "-b", "test-s")
    sh(repo, "config", "user.name", "t")
    sh(repo, "config", "user.email", "t@t")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "init")
    sh(repo, "branch", "main")
    full0 = sh(repo, "rev-parse", "HEAD")
    stub = tmp / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    slog = tmp / "stub.log"
    cfg = Config(bus_dir=bus, repo=repo, runner_dir=repo, claude_cmd=[sys.executable, str(stub)], batch_wait_sec=0,
                 test_python=sys.executable, core_tests=[], daily_cap=50, cooldown_error=0, apply_branch="test-s",
                 extra_env={"STUB_LOG": str(slog)})
    tg = FakeTG()
    rx = Receiver(cfg, tg, now=lambda: 1_800_000_000.0)

    def data_reset():
        import shutil
        shutil.rmtree(dd, ignore_errors=True)
        (dd / "data").mkdir(parents=True)
        (dd / "ops").mkdir()
        (dd / "data" / "list.json").write_text(json.dumps({"items": list(range(10))}), encoding="utf-8")

    def run_fix(mode, sensitive=True, data=True, preset="standard"):
        sh(repo, "checkout", "-q", "-f", "test-s")
        sh(repo, "reset", "-q", "--hard", full0)
        for b in sh(repo, "branch", "--list", "auto/*").split():
            sh(repo, "branch", "-D", b.strip("* "))
        sh(repo, "clean", "-fdq", "-e", ".env.local")
        sh(repo, "worktree", "prune")
        if slog.exists():
            slog.unlink()
        data_reset()
        cfg.sensitive, cfg.data_dir = sensitive, (dd if data else None)
        cfg.extra_env["STUB_MODE"] = mode
        head = git_head(repo)
        af = AutoFix(cfg, restarter=lambda c: (True, "러너 재시작(1초)"))
        res = af.run("sig-s", {"verdict": "confirmed", "summary": "저장소 읽기 실패", "cause": "형식 불일치"}, rx._snapshot(head), head, 1, preset)
        if res.status == "committed":
            res = af.apply_and_restart(res)
        return res, head

    def purposes():
        return [json.loads(x)["purpose"] for x in slog.read_text(encoding="utf-8").splitlines()] if slog.exists() else []

    # S1) 민감 경로 끔(예전 동작) → 가드 폐기
    res, head = run_fix("", sensitive=False)
    check(res.status == "guard_fail" and any("gh_store.py" in g for g in res.guard_notes), "S1 민감 경로 끔: 저장 계층 수정은 가드 폐기")

    # S2) 민감 경로 허용 → 적용 · 표시
    res, head = run_fix("")
    md = "\n".join(res.md_lines())
    check(res.status == "applied" and res.sensitive == ["docs/SPEC.md", "src/backend/gh_store.py"], "S2 민감 경로 허용: 저장 계층 · docs 수정이 적용됨")
    check("민감 경로 수정" in md and "`src/backend/gh_store.py`" in md, "S2 보고서에 「민감 경로 수정」 표시")
    check("fixed" in (repo / "src" / "backend" / "gh_store.py").read_text(encoding="utf-8"), "S2 러너 작업 폴더에 반영")
    check(all(json.loads(x)["sensitive_rules"] for x in slog.read_text(encoding="utf-8").splitlines() if json.loads(x)["purpose"] in ("spec", "implement")),
          "S2 명세 · 구현 프롬프트에 민감 규칙(땜질 금지 등)")

    # S3) 긴급 프리셋(검증 · 검토 끔)이어도 민감 경로면 검증 · 검토를 돌린다
    res, head = run_fix("", preset="urgent")
    p = purposes()
    check(res.status == "applied" and "verify" in p and "review" in p, "S3 민감 경로 수정은 검증 · 검토를 끌 수 없음(긴급 프리셋에서도 실행)")

    # S4) 새 환경변수(새 키) → 폐기하고 사람에게 그것만 요청
    res, head = run_fix("newkey")
    check(res.status == "needs_human" and "NEW_PROVIDER_KEY" in res.note and git_head(repo) == head and not sh(repo, "branch", "--list", "auto/*"),
          "S4 새 키가 필요한 수정 → 사람 요청(커밋 · 브랜치 없음)")

    # S5) 명세에서 사람 요청 — 사유를 자르지 않는다
    res, head = run_fix("spec_human")
    check(res.status == "needs_human" and len(res.note) > 300 and res.steps[-1]["status"] == "held" and len(res.steps[-1]["note"]) <= 300,
          "S5 명세 단계 사람 요청: 보고서 사유는 원문 그대로, 단계 기록만 300자")
    check(res.note in (bus / "rx" / "fix" / "sig-s" / "SPEC.md").read_text(encoding="utf-8"), "S5 사유 원문을 SPEC.md 에 남김")

    # S6) 데이터 이전: 복사본에서 시험 → 적용 후 실제 데이터에 실행
    res, head = run_fix("mig_ok")
    md = "\n".join(res.md_lines())
    check(res.status == "applied" and res.migration == "scripts/mig.py" and "복사본) 통과" in res.tests
          and json.loads((dd / "data" / "list.json").read_text(encoding="utf-8")) == {"rows": list(range(10))}, "S6 데이터 이전: 복사본 시험 통과 → 실제 데이터 이전")
    check(any(s["id"] == "migrate" and s["status"] == "ok" for s in res.steps) and "자동 결정한 값" in md and "재시도 3회" in md and "데이터 이전" in md,
          "S6 보고서에 데이터 이전 · 자동 결정한 값")

    # S7) 실제 데이터에서 이전 실패 → 데이터 복원 + 패치 revert
    res, head = run_fix("mig_fail_real")
    check(res.status == "reverted" and json.loads((dd / "data" / "list.json").read_text(encoding="utf-8")) == {"items": list(range(10))}
          and "None" in (repo / "src" / "backend" / "gh_store.py").read_text(encoding="utf-8"),
          "S7 실제 이전 실패 → 데이터 백업 복원 + 패치 revert")

    # S8) 데이터 폴더가 없는데 이전이 필요 → 코드는 브랜치에 두고 이전 실행을 사람에게 요청
    res, head = run_fix("mig_ok", data=False)
    check(res.status == "needs_human" and "scripts/mig.py" in res.note and git_head(repo) == head and res.branch in sh(repo, "branch", "--list", "auto/*"),
          "S8 데이터 폴더 없음 → 적용 보류 · 이전 실행 요청 · 브랜치 보존")

    # S9) 수신기: 자동 수정이 사람 요청으로 끝나면 표시 · 알림
    sh(repo, "checkout", "-q", "-f", "test-s")
    sh(repo, "reset", "-q", "--hard", full0)
    sh(repo, "clean", "-fdq", "-e", ".env.local")
    cfg.extra_env["STUB_MODE"] = "spec_human"
    head = git_head(repo)
    res = rx._autofix("sig-h", {"verdict": "confirmed", "summary": "번역 실패", "cause": "키"}, rx._snapshot(head), head, "standard", {"severity": "ERROR"})
    check(res.status == "needs_human" and rx.human_flag("sig-h") and any("사람 조치 필요" in m and "새 API 키" in m for m in tg.msgs),
          "S9 수신기: 사람 요청 → 사람 조치 필요 표시 + 텔레그램 알림")

    # S10) 단계 이름에 실제 모델
    cfg.model_analysis = "claude-opus-5-5"
    res, head = run_fix("")
    names = {s["id"]: s["name"] for s in res.steps}
    check(names["spec"] == "명세서(Opus)" and names["verify"] == "검증(Opus)" and names["review"] == "독립 검토(Opus)" and names["implement"] == "구현(Haiku)",
          "S10 단계 이름에 실제 모델(Opus · Haiku)")
    check(sh(repo, "rev-parse", "main") == full0, "main 브랜치 불변")
    print("모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
