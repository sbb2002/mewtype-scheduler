"""동작 모드(자동/반자동/끔)와 패치 계획 승인 흐름 self-test — 임시 git 저장소 + 가짜 claude · 텔레그램 · 재시작.

    python -m src.busrx.selftest_semi
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from src.bus import envelope as E

from .bot import BotCommands
from .policy import Policy
from .proposals import MAX_REPLANS, Proposals
from .receiver import Config, Receiver
from .selftest_fix import CALC_BAD, STUB, FakeTG
from .web import create_app, make_token


def sh(repo: Path, *a: str) -> str:
    r = subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, (a, r.stderr)
    return r.stdout.strip()


def wait(cond, timeout=90.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.2)
    return False


def main() -> int:
    def check(c, m):
        assert c, m
        print("OK ", m)

    tmp = Path(tempfile.mkdtemp(prefix="mewsemi_"))
    repo, bus = tmp / "repo", tmp / "bus"
    (repo / "src" / "backend").mkdir(parents=True)
    (repo / "src" / "collector").mkdir(parents=True)
    for d in ("src", "src/backend", "src/collector"):
        (repo / d / "__init__.py").write_text("", encoding="utf-8")
    (repo / "src" / "backend" / "calc.py").write_text(CALC_BAD, encoding="utf-8")
    (repo / ".gitignore").write_text(".env.local\n", encoding="utf-8")
    sh(repo, "init", "-q", "-b", "v4.3-fullauto")
    sh(repo, "config", "user.name", "t")
    sh(repo, "config", "user.email", "t@t")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "init")
    sh(repo, "branch", "main")
    sh(repo, "branch", "data")
    head0 = sh(repo, "rev-parse", "--short", "HEAD")
    stub = tmp / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    slog = tmp / "stub.log"
    cfg = Config(bus_dir=bus, repo=repo, runner_dir=repo, claude_cmd=[sys.executable, str(stub)], batch_wait_sec=0, stage=2,
                 test_python=sys.executable, core_tests=[], daily_cap=99, fix_daily_cap=99, cooldown_error=0, cooldown_critical=0,
                 extra_env={"STUB_LOG": str(slog), "STUB_MODE": ""})
    tg = FakeTG()
    rx = Receiver(cfg, tg)
    restarts: list[int] = []
    rx._restart = lambda c: (restarts.append(1) or (True, "러너 재시작(1초)"))
    secret = "semi-secret-0123456789"
    app = create_app(rx, cfg, tg, secret, "http://127.0.0.1:8789")
    c = app.test_client()

    def purposes():
        return [json.loads(x)["purpose"] for x in slog.read_text(encoding="utf-8").splitlines()] if slog.exists() else []

    def feed(msg, logger="src.backend.calc", sev="ERROR"):
        e = E.build_err(kind="log", severity=sev, message=msg, source={"env": "local", "service": "runner", "commit": head0},
                        logger=logger, traceback=f"Traceback...\nAssertionError: {msg}")
        rx.spool.put("err/inbox", f"{e['ts'].replace('-', '').replace(':', '')}_{e['id']}", e)
        rx.step()

    def runs(prefix: str = ""):
        rs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted((cfg.rx / "runs").glob("*.json"))]
        rs.sort(key=lambda r: r["ts"])  # 같은 초에 끝난 기록도 시간순(안정 정렬)
        return [r for r in rs if r["sig"].startswith(prefix)]

    # 1) 모드 저장 · 보존 · 초기화
    pol = rx.policy
    check(pol.mode() == "auto", "기본 모드는 자동")
    m, errs = pol.set_mode("turbo")
    check(errs and pol.mode() == "auto", "알 수 없는 모드는 거부")
    m, errs = pol.set_mode("semi", "test")
    check(not errs and Policy(cfg.rx / "policy.json", cfg).mode() == "semi", "반자동으로 변경 → 다른 인스턴스에서도 읽힘(파일 저장)")
    pol.save({"WARN": {"action": "analyze"}})
    check(pol.mode() == "semi" and pol.get("WARN")["action"] == "analyze", "정책을 저장해도 모드가 유지됨")
    check('"mode"' in (cfg.rx / "policy_history.jsonl").read_text(encoding="utf-8"), "모드 변경 이력 기록")
    pol.reset("test")
    check(pol.mode() == "auto", "정책 초기화하면 모드도 자동으로")

    # 2) 끔: 아무것도 하지 않고 기록만
    pol.set_mode("off")
    feed("모드 끔 에러", "src.backend.off1")
    check(purposes() == [] and not tg.files and any(json.loads(x).get("note") == "자동제어 꺼짐 — 분석 생략"
                                                    for x in (cfg.rx / "log.jsonl").read_text(encoding="utf-8").splitlines()), "끔: claude 호출 · 보고 없음, 기록만 남김")
    check(sh(repo, "rev-parse", "--short", "HEAD") == head0, "끔: 저장소 불변")

    # 3) 반자동: 분석 + 계획까지만 → 승인 대기
    pol.set_mode("semi")
    feed("add 결과가 틀림", "src.backend.calc")
    check(purposes() == ["analysis", "spec"], "반자동: 분석 → 계획(명세서)까지만 호출, 구현·검증은 하지 않음")
    check(sh(repo, "rev-parse", "--short", "HEAD") == head0 and not sh(repo, "branch", "--list", "auto/*"), "반자동: 코드 · 브랜치 변경 없음")
    props = rx.proposals.list()
    check(len(props) == 1 and props[0]["status"] == "pending" and props[0]["plans"][0]["rev"] == 1 and props[0]["error"]["where"] == "src.backend.calc",
          "계획안 1건이 승인 대기로 저장됨(에러 요약 포함)")
    pid = props[0]["id"]
    check("calc.add 가 뺄셈을 하던 오류 수정" in rx.proposals.plan_text(pid, 1), "계획 파일(마크다운)이 저장됨")
    pf = [f for f in tg.files if f[0].endswith("rev1.md")]
    check(pf and "승인 대기" in pf[-1][2] and "/ctl" in pf[-1][2] and "calc.add" in pf[-1][1], "텔레그램: 승인 대기 알림 + 계획 파일 첨부")
    check("승인 대기" in tg.files[-1][1] and "반자동" in tg.files[-1][1], "텔레그램: 에러 분석 보고서에도 '승인 대기(반자동)' 표시")
    r = runs()[-1]
    ids = {s["id"]: s["status"] for s in r["steps"]}
    check(ids["analysis"] == "ok" and ids["spec"] == "ok" and ids["approval"] == "held" and r["fix_status"] == "awaiting_approval" and r["proposal_id"] == pid,
          "실행 기록: 분석 ✓ · 계획 ✓ · 사용자 승인 ‘대기’")

    # 4) 정책이 '분석만'이면 반자동이어도 계획안을 만들지 않음
    pol.save({"ERROR": {"action": "analyze"}})
    n0 = len(purposes())
    feed("분석만 에러", "src.backend.only")
    check(purposes()[n0:] == ["analysis"] and len(rx.proposals.list()) == 1, "정책 ‘분석만’: 계획안 없음")
    pol.save({"ERROR": {"action": "fix"}})
    # 수정 대상이 아니면 계획안 없이 분석 보고만
    cfg.extra_env["STUB_MODE"] = "notfixable"
    n0 = len(purposes())
    feed("외부 서비스 오류", "src.backend.ext")
    check(purposes()[n0:] == ["analysis", "spec"] and len(rx.proposals.list()) == 1 and {s["id"]: s["status"] for s in runs("src.backend.ext")[-1]["steps"]}["spec"] == "stop",
          "수정 대상이 아니면 계획안을 만들지 않음(명세서 단계에서 중단 표시)")
    cfg.extra_env["STUB_MODE"] = ""

    # 5) 반려(재계획)
    ok, msg = rx.proposal_replan(pid, "ab")
    check(not ok and "사유" in msg and rx.proposals.get(pid)["status"] == "pending", "반려 사유가 너무 짧으면 거부")
    ok, msg = rx.proposal_replan(pid, "tests 도 같이 고쳐 주세요")
    check(ok and rx.proposals.get(pid)["status"] in ("replanning", "pending"), "반려 접수 → 재계획 시작")
    check(wait(lambda: len(rx.proposals.get(pid)["plans"]) == 2 and rx.proposals.get(pid)["status"] == "pending"), "재계획 완료 → 새 판(rev 2)이 승인 대기로")
    p = rx.proposals.get(pid)
    check(p["plans"][1]["feedback"] == "tests 도 같이 고쳐 주세요" and "재계획" in p["plans"][1]["title"] and "replan" in purposes(), "새 판에 반려 사유가 기록되고 재계획 호출(purpose=replan)")
    check(rx.proposals.plan_text(pid, 1) and rx.proposals.plan_text(pid, 2) and tg.files[-1][0].endswith("rev2.md") and "재작성" in tg.files[-1][2], "이전 판 보존 + 새 판 파일 전송")
    check([d["action"] for d in p["decisions"]] == ["replan"], "결정 이력 기록")

    # 6) 승인 → 파이프라인 실행(계획 재작성 없이 구현부터)
    n0 = len(purposes())
    ok, msg = rx.proposal_approve(pid)
    check(ok, "승인 접수")
    ok2, msg2 = rx.proposal_approve(pid)
    check(not ok2 and ("running" in msg2 or "done" in msg2), "중복 승인(두 번 클릭)은 거부")
    check(wait(lambda: rx.proposals.get(pid)["status"] in ("done", "failed")), "승인된 계획 실행 완료")
    p = rx.proposals.get(pid)
    after = purposes()[n0:]
    check(p["status"] == "done" and p["result"]["fix_status"] == "applied" and "spec" not in after and "replan" not in after
          and after.count("implement") == 1 and "verify" in after and "review" in after, "승인 후: 명세서 재작성 없이 구현 → 검증 → 검토 → 적용")
    check(sh(repo, "rev-parse", "--short", "HEAD") != head0 and "a + b" in (repo / "src" / "backend" / "calc.py").read_text(encoding="utf-8") and restarts,
          "승인 후: 러너 브랜치에 적용 + 재시작(가짜)")
    last = runs()[-1]
    ids = [s["id"] for s in last["steps"]]
    spec_step = next(s for s in last["steps"] if s["id"] == "spec")
    check(ids[:3] == ["analysis", "approval", "spec"] and "승인한 계획 rev 2" in spec_step["note"], "실행 기록: 분석 → 사용자 승인 → 승인된 계획(rev 2)으로 진행")
    check(tg.files[-1][0].endswith(".md") and "패치" in tg.files[-1][1], "텔레그램: 최종 보고서 전송")
    ok3, _ = rx.proposal_decline(pid)
    check(not ok3, "이미 처리된 계획안은 거절 불가")

    # 7) 거절 + 같은 에러 재제안 억제(쿨다운)
    sh(repo, "reset", "-q", "--hard", head0)
    pol.save({"ERROR": {"cooldown_sec": 3600}})
    feed("거절할 에러", "src.backend.decl")
    pid2 = rx.proposals.list()[0]["id"]
    check(rx.proposals.get(pid2)["status"] == "pending", "새 에러 → 새 계획안")
    n0 = len(purposes())
    ok, msg = rx.proposal_decline(pid2, "지금은 필요 없음")
    check(ok and rx.proposals.get(pid2)["status"] == "declined" and purposes()[n0:] == [], "거절: 파이프라인 실행 없음, 상태 declined")
    n_props = len(rx.proposals.list())
    feed("거절할 에러", "src.backend.decl")
    check(len(rx.proposals.list()) == n_props and len(purposes()) == n0, "거절한 에러는 쿨다운 동안 다시 제안하지 않음")
    pol.save({"ERROR": {"cooldown_sec": 0}})

    # 8) 계획 이후 코드가 바뀐 뒤 승인
    feed("오래된 계획", "src.backend.stale")
    pid3 = rx.proposals.list()[0]["id"]
    (repo / "src" / "backend" / "other.py").write_text("X = 1\n", encoding="utf-8")
    sh(repo, "add", "-A")
    sh(repo, "commit", "-q", "-m", "other change")
    rx.proposal_approve(pid3)
    check(wait(lambda: rx.proposals.get(pid3)["status"] in ("done", "failed")), "코드가 바뀐 뒤 승인한 계획도 실행됨")
    check(rx.proposals.get(pid3)["result"]["stale_base"] is True, "base 가 바뀌었음을 결과에 기록(현재 코드 기준으로 실행)")

    # 9) 재계획 상한 · 중단 복구
    feed("재계획 상한", "src.backend.maxrp")
    pid4 = rx.proposals.list()[0]["id"]
    for _ in range(MAX_REPLANS):
        rx.proposals.add_revision(pid4, {"title": "t", "change_plan": [], "test_plan": "", "risk": "", "spec_md": "x"}, "r")
    ok, msg = rx.proposal_replan(pid4, "또 반려")
    check(not ok and str(MAX_REPLANS) in msg, "재계획 횟수 상한")
    rx.proposals.update(pid4, status="running")
    check(Proposals(cfg.rx / "proposals").recover() >= 1 and rx.proposals.get(pid4)["status"] == "interrupted", "처리 중 종료된 계획안은 재기동 때 interrupted 로 표시")

    # 10) 웹 API
    check(c.get("/api/proposals").status_code == 401, "미인증 /api/proposals 는 401")
    c.get("/auth?t=" + make_token(secret, time.time()))
    h = {"X-CSRF": c.get("/api/me").get_json()["csrf"]}
    feed("웹에서 결정", "src.backend.web")
    pid5 = [p for p in rx.proposals.list() if p["status"] == "pending"][0]["id"]
    lst = c.get("/api/proposals").get_json()
    check(lst["pending"] >= 1 and any(p["id"] == pid5 for p in lst["proposals"]) and lst["head_now"] and lst["max_replans"] == MAX_REPLANS, "API: 목록 · 대기 건수 · 현재 HEAD")
    g = c.get(f"/api/proposals/{pid5}").get_json()
    check("1" in g["plan_texts"] and g["proposal"]["error"]["message"], "API: 상세 + 계획 파일 본문")
    check(c.get("/api/proposals/not-an-id").status_code == 400 and c.get("/api/proposals/" + "0" * 26).status_code == 404, "API: 잘못된 id 400 · 없는 id 404")
    check(c.post(f"/api/proposals/{pid5}/approve").status_code == 403, "API: CSRF 없는 결정은 403")
    r = c.post(f"/api/proposals/{pid5}/replan", json={"reason": "x"}, headers=h)
    check(r.status_code == 400, "API: 반려 사유가 짧으면 400")
    r = c.post(f"/api/proposals/{pid5}/decline", json={"note": "테스트"}, headers=h)
    check(r.status_code == 200 and r.get_json()["ok"] and rx.proposals.get(pid5)["status"] == "declined", "API: 거절")
    r = c.post(f"/api/proposals/{pid5}/approve", headers=h)
    check(r.status_code == 409 and r.get_json()["errors"], "API: 이미 처리된 계획안 승인은 409")
    check(c.post("/api/mode", json={"mode": "turbo"}, headers=h).status_code == 400, "API: 알 수 없는 모드 400")
    r = c.post("/api/mode", json={"mode": "off"}, headers=h).get_json()
    check(r["ok"] and r["mode"] == "off" and c.get("/api/status").get_json()["mode"] == "off", "API: 모드 변경이 현황에 반영")
    c.post("/api/mode", json={"mode": "semi"}, headers=h)
    check(c.get("/api/status").get_json()["proposals_pending"] == rx.proposals.pending_count(), "API: 현황에 승인 대기 건수")

    # 11) 텔레그램 /automode
    bot = BotCommands(rx, cfg, tg, None, "424242")

    def say(text, chat="424242"):
        bot.handle({"update_id": 1, "message": {"text": text, "chat": {"id": int(chat), "type": "private"}}})

    say("/automode")
    check("반자동(semi)" in tg.msgs[-1] and "/automode auto" in tg.msgs[-1], "/automode: 현재 모드와 사용법")
    say("/automode auto")
    check(rx.policy.mode() == "auto" and "자동" in tg.msgs[-1], "/automode auto: 변경")
    say("/automode turbo")
    check("mode" in tg.msgs[-1] and rx.policy.mode() == "auto", "/automode 잘못된 값은 거부")
    n = len(tg.msgs)
    say("/automode off", chat="999")
    check(len(tg.msgs) == n and rx.policy.mode() == "auto", "/automode: 허용되지 않은 채팅은 무응답")
    say("/auto")
    check("모드 자동" in tg.msgs[-1], "/auto 현황에 모드 표시")
    print("모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
