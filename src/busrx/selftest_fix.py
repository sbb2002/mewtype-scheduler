"""2단계(자동 수정) self-test — 임시 git 저장소 + 가짜 claude(스텁) + 가짜 텔레그램 · 가짜 재시작 (네트워크 · 모델 호출 없음).

    python -m src.busrx.selftest_fix
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from src.bus import envelope as E

from . import guard
from . import pipelines as P
from .autofix import AutoFix
from .receiver import Config, Receiver, git_head

STUB = r'''
import json, os, re, sys
prompt = sys.stdin.read()
_n = os.path.join(os.path.dirname(os.environ["STUB_LOG"]), "util.txt")
try:
    u = int(open(_n).read())
except Exception:
    u = 45
u += 1
open(_n, "w").write(str(u))
print(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {
    "five_hour": {"utilization": u / 100, "resetsAt": 1791784800}, "seven_day": {"utilization": 0.54, "resetsAt": 1791799200}}}}))
argv = sys.argv[1:]
purpose = (re.search(r"\[\[PURPOSE:(\w+)\]\]", prompt) or [None, "?"])[1]
def arg(name):
    return argv[argv.index(name) + 1] if name in argv else ""
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps({"purpose": purpose, "model": arg("--model"), "tools": arg("--tools"),
                        "perm": arg("--permission-mode"), "cwd": os.getcwd()}) + "\n")
mode = os.environ.get("STUB_MODE", "")
CALC = os.path.join("src", "backend", "calc.py")
GOOD = "def add(a, b):\n    return a + b\n\nif __name__ == \"__main__\":\n    assert add(1, 2) == 3\n    print('ok')\n"
def out(d):
    print(json.dumps({"structured_output": d, "total_cost_usd": 0.01, "is_error": False, "result": ""}))
if purpose == "analysis":
    out({"verdict": "confirmed", "summary": "calc.add 가 뺄셈", "cause": "add 가 a-b 를 반환", "evidence": ["src/backend/calc.py:2 — a - b"],
         "proposed_action": "a + b 로 수정"})
elif purpose in ("spec", "replan"):
    out({"fixable": mode != "notfixable", "why_not": "외부 서비스 일시 오류라 코드 수정 대상 아님",
         "title": "calc.add 가 뺄셈을 하던 오류 수정" + (" (사용자 지적 반영 재계획)" if purpose == "replan" else ""),
         "change_plan": [{"file": "src/backend/calc.py", "change": "a - b 를 a + b 로"}], "test_plan": "self-test", "risk": "낮음"})
elif purpose in ("implement", "revise"):
    if mode == "syntax_then_fix" and purpose == "implement":
        open(CALC, "w", encoding="utf-8").write("def add(a, b)\n    return a + b\n")
    elif mode == "forbidden":
        os.makedirs(os.path.join("src", "bus"), exist_ok=True)
        open(os.path.join("src", "bus", "evil.py"), "w", encoding="utf-8").write("X = 1\n")
        open(CALC, "w", encoding="utf-8").write(GOOD)
    elif mode == "prod":
        open(CALC, "w", encoding="utf-8").write(GOOD + "URL = 'https://mewtype-schduler.vercel.app/x'\n")
    elif mode == "newprovider":
        open(CALC, "w", encoding="utf-8").write("import os\n" + GOOD + "URL = 'https://api.openrouter.ai/v1/chat'\nKEY = os.environ.get('OPENROUTER_API_KEY')\n")
    else:
        open(CALC, "w", encoding="utf-8").write(GOOD)
    print(json.dumps({"result": "수정 완료", "total_cost_usd": 0.02, "is_error": False}))
elif purpose == "verify":
    out({"approve": mode != "verify_reject", "issues": ["명세서와 다름(스텁)"] if mode == "verify_reject" else [], "summary": "명세서와 일치"})
elif purpose == "review":
    rej = mode in ("review_reject", "review_prod")
    out({"approve": not rej, "concerns": ["부작용 우려(스텁)"] if rej else [], "touches_prod_resources": mode == "review_prod",
         "summary": "독립 검토 완료"})
else:
    sys.exit(3)
'''

CALC_BAD = "def add(a, b):\n    return a - b\n\nif __name__ == \"__main__\":\n    assert add(1, 2) == -1\n    print('ok')\n"


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

    tmp = Path(tempfile.mkdtemp(prefix="mewfix_"))
    repo, bus = tmp / "repo", tmp / "bus"
    (repo / "src" / "backend").mkdir(parents=True)
    (repo / "src" / "collector").mkdir(parents=True)
    for d in ("src", "src/backend", "src/collector"):
        (repo / d / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "backend" / "calc.py").write_text(CALC_BAD, encoding="utf-8")
    (repo / ".env.local").write_text("TELEGRAM_BOT_TOKEN=local-only-token-value\n", encoding="utf-8")
    (repo / ".gitignore").write_text(".env.local\n", encoding="utf-8")
    sh(repo, "init", "-q", "-b", "v4.3-fullauto")
    sh(repo, "config", "user.name", "t")
    sh(repo, "config", "user.email", "t@t")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "init")
    sh(repo, "branch", "main")
    sh(repo, "branch", "data")
    sh(repo, "remote", "add", "origin", "https://example.invalid/prod.git")
    base0 = sh(repo, "rev-parse", "--short", "HEAD")
    full0 = sh(repo, "rev-parse", "HEAD")
    stub = tmp / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    slog = tmp / "stub.log"
    cfg = Config(bus_dir=bus, repo=repo, runner_dir=repo, claude_cmd=[sys.executable, str(stub)], batch_wait_sec=0,
                 test_python=sys.executable, core_tests=[], daily_cap=50, cooldown_error=0,
                 extra_env={"STUB_LOG": str(slog)})
    tg = FakeTG()
    clock = [1_800_000_000.0]
    rx = Receiver(cfg, tg, now=lambda: clock[0])
    restarts: list[int] = []

    def fake_restart(c):
        restarts.append(1)
        return True, "러너 재시작(1초)"

    def reset():
        sh(repo, "checkout", "-q", "-f", "v4.3-fullauto")
        sh(repo, "reset", "-q", "--hard", full0)
        for b in sh(repo, "branch", "--list", "auto/*").split():
            sh(repo, "branch", "-D", b.strip("* "))
        sh(repo, "clean", "-fdq", "-e", ".env.local")
        sh(repo, "worktree", "prune")

    def calls():
        return [json.loads(x) for x in slog.read_text(encoding="utf-8").splitlines()] if slog.exists() else []

    def run_fix(mode="", restart=fake_restart, apply_branch="v4.3-fullauto", seq=1, preset="standard"):
        reset()
        cfg.extra_env["STUB_MODE"] = mode
        cfg.apply_branch = apply_branch
        head = git_head(repo)
        snap = rx._snapshot(head)
        af = AutoFix(cfg, restarter=restart)
        analysis = {"verdict": "confirmed", "summary": "calc.add 가 뺄셈", "cause": "add 가 a-b", "evidence": [], "proposed_action": ""}
        res = af.run("sig-test", analysis, snap, head, seq, preset)
        if res.status == "committed":
            res = af.apply_and_restart(res)
        return res, head

    # S1) Receiver 전체 경로 (분석 → 수정 → 적용 → 재시작 → 텔레그램)
    rx._restart = lambda c: fake_restart(c)
    env = E.build_err(kind="log", severity="ERROR", message="add 결과가 틀림", source={"env": "local", "service": "runner", "commit": base0},
                      logger="src.backend.calc", traceback="Traceback...\nAssertionError: add")
    rx.spool.put("err/inbox", f"{env['ts'].replace('-', '').replace(':', '')}_{env['id']}", env)
    cfg.extra_env["STUB_MODE"] = ""
    check(rx.step() == 1, "S1 ERROR 봉투 처리")
    def rep_text():  # 텔레그램으로 간 마지막 보고: 캡션 + 첨부 파일 내용
        f = tg.files[-1]
        return f[2] + "\n" + f[1]

    m = rep_text()
    new_head = sh(repo, "rev-parse", "--short", "HEAD")
    check(new_head != base0, "S1 러너 작업 브랜치가 수정 커밋으로 전진(ff 적용)")
    check("a + b" in (repo / "src" / "backend" / "calc.py").read_text(encoding="utf-8"), "S1 러너 작업 폴더에 수정 반영")
    check(len(restarts) == 1, "S1 적용 후 러너 재시작 1회")
    check("calc.add 가 뺄셈을 하던 오류 수정" in m and "(`v4.3.1`)" in m, "S1 텔레그램: 패치 1줄 요약 + 버전")
    check("합계 1개 파일 · +" in m and "| `src/backend/calc.py` | +" in m and "| **합계 (1개)** |" in m, "S1 텔레그램: 파일별 +/− 와 합계")
    check(f"커밋: {base0} → {new_head}" in m, "S1 텔레그램: 커밋 이전 → 이후(수정 커밋)")
    check("금지 자원 확인**: ✅ 통과" in m and "Vercel" in m and "GCP" in m and "텔레그램 번호" in m, "S1 텔레그램: 금지 자원 확인 항목 명시")
    check("claude-haiku-5-5(구현)" in m and "claude-sonnet-5-5" in m, "S1 텔레그램: 모델 배정 표시")
    check("검증자: 승인" in m and "검토자: 승인" in m and "러너 재시작" in m, "S1 검증 · 검토 · 재시작 결과 표시")
    check("세션(5시간)**:" in m and "주간(7일)**: 54% 사용 · 남음 46%" in m and "이번 처리 +" in m, "S1 사용량(세션 · 주간 · 이번 처리) 표시")
    rep = [json.loads(p.read_text(encoding="utf-8")) for p in rx.spool.list("report/inbox")][-1]
    check(rep["usage"]["seven"] == 0.54 and rep["usage"]["calls_seen"] >= 4 and rep["usage"]["delta_five"] > 0, "S1 report 봉투에 usage 기록")
    check(rep["files_changed"][0]["path"] == "src/backend/calc.py" and rep["lines_added"] >= 1 and rep["applied"] and rep["guard_ok"]
          and rep["commit_after"] == new_head, "S1 report 봉투에 파일별 변경 · 합계 · 적용 · 가드 · 커밋 기록")
    c = calls()
    by = {x["purpose"]: x for x in c}
    check(by["implement"]["model"] == "claude-haiku-5-5" and by["implement"]["perm"] == "acceptEdits", "S1 구현은 Haiku 5.5 (acceptEdits)")
    check(all(by[p]["model"] == "claude-sonnet-5-5" for p in ("analysis", "spec", "verify", "review")), "S1 분석·명세·검증·검토는 Sonnet 5.5")
    check("Bash" not in by["implement"]["tools"] and by["implement"]["tools"] == "Read,Grep,Glob,Edit,Write", "S1 Haiku 에게 셸 도구 없음")
    check(by["verify"]["tools"] == by["review"]["tools"] == "Read,Grep,Glob", "S1 검증 · 검토는 읽기 전용")
    check(sh(repo, "rev-parse", "main") == full0 and sh(repo, "rev-parse", "data") == full0, "S1 main · data 브랜치 불변")
    check("auto/" in sh(repo, "branch", "--list", "auto/*"), "S1 수정 브랜치(auto/…)가 로컬에 남음")
    check("local-only" in (repo / ".env.local").read_text(encoding="utf-8"), "S1 환경 파일 불변")
    run = json.loads(sorted((bus / "rx" / "runs").glob("*.json"))[-1].read_text(encoding="utf-8"))
    ids = [s["id"] for s in run["steps"]]
    check(ids == ["analysis", "spec", "worktree", "implement", "guard", "tests", "verify", "review", "commit", "protected", "apply", "restart"]
          and all(s["status"] == "ok" for s in run["steps"]) and run["action"] == "fix" and run["preset"] == "standard",
          "S1 실행 기록(runs): 단계 순서 · 모두 통과 · 정책(fix/표준)")
    check(run["steps"][3]["model"] == "claude-haiku-5-5" and run["steps"][1]["model"] == "claude-sonnet-5-5", "S1 실행 기록에 단계별 모델")

    # S2) 금지 경로 → 폐기
    res, head = run_fix("forbidden")
    check(res.status == "guard_fail" and any("금지 경로" in g for g in res.guard_notes) and not res.guard_ok, "S2 금지 경로(src/bus) 수정은 가드가 폐기")
    check(git_head(repo) == head and not sh(repo, "branch", "--list", "auto/*"), "S2 폐기 시 커밋 · 브랜치 없음")
    # S3) 운영 자원(Vercel 주소) 추가
    res, head = run_fix("prod")
    check(res.status == "guard_fail" and any("Vercel" in g for g in res.guard_notes), "S3 Vercel 주소 추가는 가드가 폐기")
    # S3b) 공급자 교체(새 외부 호스트 + 새 환경변수 이름) → 폐기 (운영자 지시 2026-10-13)
    res, head = run_fix("newprovider")
    check(res.status == "guard_fail" and any("새 외부 호스트" in g for g in res.guard_notes) and any("새 환경변수" in g for g in res.guard_notes),
          "S3b 새 외부 호스트 · 환경변수 이름(공급자 교체)을 끌어들이는 수정은 가드가 폐기")
    check(git_head(repo) == head and not sh(repo, "branch", "--list", "auto/*"), "S3b 폐기 시 커밋 · 브랜치 없음")
    # S4) 수정 라운드 1회 (첫 시도 문법 오류 → 지적 반영)
    n_before = len(calls())
    res, head = run_fix("syntax_then_fix")
    impl = [x for x in calls()[n_before:] if x["purpose"] in ("implement", "revise")]
    check(res.status == "applied" and res.revisions == 1 and [x["purpose"] for x in impl] == ["implement", "revise"], "S4 컴파일 실패 → Haiku 수정 라운드 1회 후 통과")
    # S5) 검토자 반려 2회 → 미적용
    res, head = run_fix("review_reject")
    check(res.status == "rejected" and not res.head and git_head(repo) == head, "S5 검토자 반려가 반복되면 커밋 없이 종료")
    res, head = run_fix("verify_reject")
    check(res.status == "rejected", "S5 검증자 반려도 동일")
    # S6) 검토자가 운영 자원 접촉 지적 → 즉시 폐기
    res, head = run_fix("review_prod")
    check(res.status == "guard_fail" and res.revisions == 0, "S6 검토자의 운영 자원 접촉 지적은 수정 라운드 없이 폐기")
    # S7) 수정 대상 아님
    res, head = run_fix("notfixable")
    check(res.status == "not_fixable" and not res.files and any("커밋: " + head + " → " + head in ln for ln in res.lines()), "S7 수정 대상 아님 → 변경 없음 보고")
    # S8) 미커밋 변경과 겹치면 적용 보류
    reset()
    (repo / "src" / "backend" / "calc.py").write_text(CALC_BAD + "# 사용자 편집\n", encoding="utf-8")
    cfg.extra_env["STUB_MODE"] = ""
    head = git_head(repo)
    snap = rx._snapshot(head)
    af = AutoFix(cfg, restarter=fake_restart)
    res = af.run("sig-test", {"verdict": "confirmed", "cause": "x"}, snap, head, 9)
    res = af.apply_and_restart(res)
    check(res.status == "held" and "미커밋 변경" in res.note and git_head(repo) == head, "S8 사용자의 미커밋 변경과 겹치면 적용 보류(브랜치는 보존)")
    # S9) 적용 후 건강 확인 실패 → 자동 revert
    seq_calls = []

    def flaky(c):
        seq_calls.append(1)
        return (False, "러너 재시작(5초) — 건강 확인 실패") if len(seq_calls) == 1 else (True, "러너 재시작(2초)")

    res, head = run_fix("", restart=flaky)
    txt = (repo / "src" / "backend" / "calc.py").read_text(encoding="utf-8")
    check(res.status == "reverted" and "a - b" in txt and len(seq_calls) == 2 and "Revert" in sh(repo, "log", "-1", "--format=%s"),
          "S9 건강 확인 실패 시 자동 revert + 재시작")
    # S10) 러너가 안 떠 있으면 적용만
    res, head = run_fix("", restart=lambda c: (False, "러너가 실행 중이 아님 — 재시작 생략"))
    check(res.status == "applied_no_restart" and res.applied and not res.restarted, "S10 러너 미실행이면 재시작 생략하고 적용만")
    # S11) 적용 브랜치 불일치
    res, head = run_fix("", apply_branch="other")
    check(res.status == "held" and git_head(repo) == head, "S11 러너 브랜치가 기대와 다르면 적용 보류")
    # S13) 긴급 프리셋: 검증·검토 건너뜀(가드는 그대로), 변경 모듈 self-test 만
    n_before = len(calls())
    res, head = run_fix("", preset="urgent")
    purposes = [x["purpose"] for x in calls()[n_before:]]
    sk = {s["id"]: s["status"] for s in res.steps}
    check(res.status == "applied" and "verify" not in purposes and "review" not in purposes and purposes.count("implement") == 1,
          "S13 긴급 프리셋: 검증 · 독립 검토 호출 없이 적용")
    check(sk["verify"] == "skipped" and sk["review"] == "skipped" and sk["guard"] == "ok" and sk["protected"] == "ok", "S13 검증/검토는 건너뜀, 가드·보호 확인은 그대로")
    res, head = run_fix("prod", preset="urgent")
    check(res.status == "guard_fail" and any("Vercel" in g for g in res.guard_notes), "S13 긴급 프리셋에서도 금지 자원 가드는 동작")
    res, head = run_fix("forbidden", preset="urgent")
    check(res.status == "guard_fail" and any("금지 경로" in g for g in res.guard_notes), "S13 긴급 프리셋에서도 금지 경로 가드는 동작")
    # S14~S18) 사용자 정의 파이프라인(블록 조립)대로 엔진이 도는지
    import copy as _copy

    def pl(**over):
        b = _copy.deepcopy(P.BUILTIN["standard"]["blocks"])
        for x in b:
            if x["id"] in over:
                x.update(over[x["id"]])
        return b

    sw = pl()
    vi, ri = [x["id"] for x in sw].index("verify"), [x["id"] for x in sw].index("review")
    sw[vi], sw[ri] = sw[ri], sw[vi]
    check(P.save_custom(cfg, "swap", "검토 먼저", sw) == [], "S14 준비: 검토를 검증보다 먼저 놓은 파이프라인 저장")
    res, head = run_fix("", preset="swap")
    ids = [s["id"] for s in res.steps]
    check(res.status == "applied" and ids.index("review") < ids.index("verify") < ids.index("commit"), "S14 엔진이 조립된 순서대로 실행(검토 → 검증 → 커밋)")
    check(res.preset == "swap", "S14 결과에 사용한 파이프라인 id 기록")

    P.save_custom(cfg, "norev", "라운드 없음", pl(implement={"params": {"max_revisions": 0}}))
    n_before = len(calls())
    res, head = run_fix("syntax_then_fix", preset="norev")
    purposes = [x["purpose"] for x in calls()[n_before:]]
    check(res.status == "tests_fail" and "revise" not in purposes and res.revisions == 0 and git_head(repo) == head and not res.head,
          "S15 max_revisions=0: 문법 오류 첫 시도에서 수정 라운드 없이 폐기")
    P.save_custom(cfg, "twice", "라운드 2회", pl(implement={"params": {"max_revisions": 2}}))
    res, head = run_fix("syntax_then_fix", preset="twice")
    check(res.status == "applied" and res.revisions == 1, "S15 max_revisions=2: 수정 라운드를 쓰면 통과(1회 사용)")

    P.save_custom(cfg, "noapply", "커밋까지만", pl(apply={"enabled": False}, restart={"enabled": False}))
    r_before = len(restarts)
    res, head = run_fix("", preset="noapply")
    sk = {s["id"]: s for s in res.steps}
    check(res.status == "committed" and not res.applied and git_head(repo) == head and len(restarts) == r_before
          and sk["apply"]["status"] == "skipped" and "파이프라인에서 끔" in sk["apply"]["note"] and sh(repo, "branch", "--list", "auto/*"),
          "S16 적용 블록 끔: 로컬 커밋까지만, 러너 브랜치 · 재시작 불변")
    P.save_custom(cfg, "norestart", "적용만", pl(restart={"enabled": False}))
    res, head = run_fix("", preset="norestart")
    check(res.status == "applied_no_restart" and res.applied and not res.restarted and len(restarts) == r_before
          and "a + b" in (repo / "src" / "backend" / "calc.py").read_text(encoding="utf-8"), "S17 재시작 블록 끔: 적용은 하고 러너는 재시작하지 않음")

    P.save_custom(cfg, "bare", "검증 없음", pl(verify={"enabled": False}, review={"enabled": False}))
    n_before = len(calls())
    res, head = run_fix("", preset="bare")
    purposes = [x["purpose"] for x in calls()[n_before:]]
    sk = {s["id"]: s for s in res.steps}
    check(res.status == "applied" and "verify" not in purposes and "review" not in purposes and sk["guard"]["status"] == "ok" and sk["protected"]["status"] == "ok",
          "S18 검증 · 검토를 끈 사용자 정의도 가드 · 보호 확인은 그대로")
    res, head = run_fix("prod", preset="bare")
    check(res.status == "guard_fail" and any("Vercel" in g for g in res.guard_notes), "S18 검증 없는 파이프라인에서도 금지 자원 가드 동작")
    # 존재하지 않는 id 는 표준으로 안전하게
    res, head = run_fix("", preset="없는파이프라인")
    check(res.preset == "standard" and res.status == "applied", "S18 없는 파이프라인 id 는 표준으로 대체")
    # S12) 적용 끔
    cfg.apply_local = False
    res, head = run_fix("")
    cfg.apply_local = True
    check(res.status == "committed" and not res.applied and git_head(repo) == head and sh(repo, "branch", "--list", "auto/*"),
          "S12 RX_APPLY_LOCAL=0 이면 로컬 브랜치에만 커밋")

    # 가드 단위
    check(guard.path_violations(["src/backend/storage.py", "src/frontend/index.html", "src/backend/x.py", "src/bus/a.py"]) ==
          ["금지 경로 수정: src/backend/storage.py", "허용 범위 밖 경로 수정: src/frontend/index.html",
           "금지 경로 수정: src/bus/a.py"], "가드: 경로 허용/금지 판정")
    d = "+x = '1234567890:AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA'\n+import subprocess; subprocess.run(['git', 'push'])\n-# 디스클레이머 문구\n"
    v = guard.content_violations("diff\n" + d, [])
    check(any("텔레그램 봇 토큰" in x for x in v) and any("원격 git" in x for x in v) and any("디스클레이머" in x for x in v), "가드: 토큰 · git push · 디스클레이머 삭제 탐지")
    print("모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
