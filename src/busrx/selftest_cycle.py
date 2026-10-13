"""동작 주기(이벤트마다 · 1시간마다 · 3시간마다) · 묶음 대기열 · 모드 변경 시 대기열 결정 self-test (가짜 claude · 가짜 텔레그램).

    python -m src.busrx.selftest_cycle
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from src.bus import envelope as E

from .receiver import Config, Receiver, signature
from .selftest_web import STUB, FakeTG
from .web import create_app, make_token


def env(sev, msg, logger):
    return E.build_err(kind="log", severity=sev, message=msg, source={"env": "local", "service": "runner"}, logger=logger)


def main() -> int:
    def check(c, m):
        assert c, m
        print("OK ", m)

    tmp = Path(tempfile.mkdtemp(prefix="mewcyc_"))
    stub = tmp / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    stublog = tmp / "stub.log"
    wrapper = tmp / "wrap.py"
    wrapper.write_text(f"import subprocess, sys\nopen(r'{stublog}', 'a').write('x')\nr = subprocess.run([sys.executable, r'{stub}'], input=sys.stdin.buffer.read().decode('utf-8', 'replace'), text=True, "
                       f"capture_output=True, encoding='utf-8')\nsys.stdout.write(r.stdout)\n", encoding="utf-8")

    def ncalls():
        return len(stublog.read_text()) if stublog.exists() else 0

    # 시계: KST 10:30 에서 시작 (UTC 01:30)
    base = time.mktime((2026, 10, 13, 1, 30, 0, 0, 0, 0)) - time.timezone
    clock = [float(base)]
    cfg = Config(bus_dir=tmp / "bus", claude_cmd=[sys.executable, str(wrapper)], stage=1, batch_wait_sec=0, cooldown_error=100000,
                 cooldown_critical=300, runner_dir=tmp, daily_cap=100)
    tg = FakeTG()
    rx = Receiver(cfg, tg, now=lambda: clock[0])
    sp, pol = rx.spool, rx.policy
    pol.save({"WARN": {"action": "analyze", "cooldown_sec": 0}})
    check(not hasattr(cfg, "fix_daily_cap"), "수정 일일 상한 설정이 없어짐")

    def feed(e, step=True):
        sp.put("err/inbox", f"{e['ts'].replace('-', '').replace(':', '')}_{e['id']}", e)
        if step:
            rx.step()

    # 1) 기본값 · 저장 보존
    check(pol.cycle() == "event", "기본 동작 주기 = 이벤트 발생 시마다")
    r = rx.change_cycle("h1")
    check(r["ok"] and pol.cycle() == "h1" and json.loads((cfg.rx / "policy.json").read_text(encoding="utf-8"))["cycle"] == "h1", "주기 저장")
    pol.set_mode("semi")
    pol.set_mode("auto")
    pol.save({"ERROR": {"record": True}})
    check(pol.cycle() == "h1" and pol.mode() == "auto", "모드 · 정책 저장이 주기를 지우지 않음")
    check(not rx.change_cycle("h9")["ok"], "잘못된 주기는 거부")

    # 2) 1시간 주기: CRITICAL 즉시 / 나머지는 보류
    n0 = ncalls()
    feed(env("ERROR", "에러 하나", "src.backend.cyc_a"))
    feed(env("WARN", "경고 하나", "src.backend.cyc_b"))
    check(ncalls() == n0 and sp.count("err/hold") == 2 and sp.count("err/inbox") == 0, "ERROR · WARN 은 처리하지 않고 보류 폴더에 모임")
    check(rx.queue_info() == {"count": 2, "types": 2}, "대기열: 2건 / 2종류")
    feed(env("ERROR", "에러 하나", "src.backend.cyc_a"))
    check(rx.queue_info() == {"count": 3, "types": 2}, "같은 종류는 건수만 늘고 종류 수는 그대로")
    feed(env("CRITICAL", "치명 하나", "src.backend.cyc_crit"))
    check(ncalls() == n0 + 1 and sp.count("err/hold") == 3, "CRITICAL 은 주기와 관계없이 즉시 처리")
    nxt = rx.next_run_epoch()
    check(nxt is not None and nxt - clock[0] == 1800, "다음 실행 = 다음 정시(10:30 → 11:00, 30분 뒤)")

    # 3) 정시 전에는 비우지 않고, 정시가 지나면 같은 종류끼리 묶어 한 번씩
    rx._maybe_flush()
    check(sp.count("err/hold") == 3 and ncalls() == n0 + 1, "정시 전에는 처리하지 않음")
    clock[0] += 1801
    rx._maybe_flush()
    check(sp.count("err/hold") == 0 and ncalls() == n0 + 3, "정시가 지나면 보류분을 종류별 1회씩 처리(ERROR 1 + WARN 1, 중복 ERROR 는 묶음)")
    rx._maybe_flush()
    check(ncalls() == n0 + 3, "같은 구간에서 두 번 처리하지 않음")

    # 4) 묶음 주기에서는 쿨다운을 쓰지 않는다(CRITICAL 은 쓴다)
    feed(env("ERROR", "에러 하나", "src.backend.cyc_a"))
    clock[0] += 3601
    n1 = ncalls()
    rx._maybe_flush()
    check(ncalls() == n1 + 1, "쿨다운(100000초) 안이어도 다음 주기에 같은 종류를 다시 처리")
    feed(env("CRITICAL", "치명 하나", "src.backend.cyc_crit"))
    check(ncalls() == n1 + 2, "CRITICAL 은 쿨다운(5분)이 지났으면 다시 즉시 처리")
    clock[0] += 60
    feed(env("CRITICAL", "치명 하나", "src.backend.cyc_crit"))
    check(ncalls() == n1 + 2, "CRITICAL 은 묶음 주기에서도 쿨다운(5분)은 그대로 적용 — 1분 뒤 재발은 생략")

    # 5) 3시간 주기: 0 · 3 · 6 … 시 정각
    rx.change_cycle("h3")
    feed(env("ERROR", "에러 셋", "src.backend.cyc_c"))
    check(sp.count("err/hold") == 1, "3시간 주기도 보류")
    nxt = rx.next_run_epoch()
    kst_hour = int(((nxt + 9 * 3600) % 86400) // 3600)
    check(kst_hour % 3 == 0 and 0 < nxt - clock[0] <= 10800, "다음 실행은 3의 배수 시 정각")
    r = rx.change_cycle("h1")
    check(sp.count("err/hold") == 1, "묶음끼리 바꾸면 보류분은 그대로 두고 다음 정시부터")

    # 6) 모드 변경 + 대기열: 결정이 필요 → 버림
    r = rx.change_mode("semi")
    check(not r["ok"] and r.get("needs_queue") and r["count"] == 1 and r["types"] == 1 and pol.mode() == "auto", "대기열이 있으면 결정 없이는 모드를 바꾸지 않음")
    n2 = ncalls()
    r = rx.change_mode("semi", "discard")
    check(r["ok"] and pol.mode() == "semi" and sp.count("err/hold") == 0 and ncalls() == n2, "아니오(버림): 처리 없이 비우고 모드 변경")
    logs = (cfg.rx / "log.jsonl").read_text(encoding="utf-8")
    check("모드 변경으로 대기 중이던 에러를 버림" in logs, "버린 건은 로그에 남음")
    r = rx.change_mode("auto")
    check(r["ok"] and pol.mode() == "auto", "대기열이 비면 바로 변경")

    # 7) 모드 변경 + 대기열 → 먼저 처리
    feed(env("ERROR", "에러 넷", "src.backend.cyc_d"))
    check(sp.count("err/hold") == 1, "다시 보류")
    n3 = ncalls()
    r = rx.change_mode("off", "process")
    check(r["ok"] and pol.mode() == "off" and sp.count("err/hold") == 0 and ncalls() == n3 + 1, "예(먼저 처리): 처리한 뒤 모드 변경")
    # 끔 모드: 보류하지 않고 바로 기록만
    feed(env("ERROR", "끔에서 온 에러", "src.backend.cyc_e"))
    check(sp.count("err/hold") == 0 and ncalls() == n3 + 1, "끔 모드에서는 보류도 분석도 하지 않음")
    pol.set_mode("auto")

    # 8) 이벤트마다로 되돌리면 쌓인 것을 바로 처리
    feed(env("ERROR", "에러 다섯", "src.backend.cyc_f"))
    check(sp.count("err/hold") == 1, "다시 보류")
    n4 = ncalls()
    rx.change_cycle("event")
    check(sp.count("err/hold") == 0 and ncalls() == n4 + 1, "이벤트마다로 바꾸면 보류분을 즉시 처리")
    feed(env("ERROR", "에러 여섯", "src.backend.cyc_g"))
    check(ncalls() == n4 + 2 and sp.count("err/hold") == 0, "이벤트마다 주기는 도착 즉시 처리")

    # 9) 관리 페이지 API
    rx.change_cycle("h1")
    feed(env("WARN", "경고 둘", "src.backend.cyc_h"))
    app = create_app(rx, cfg, tg, "cyc-secret-0123456789", "http://127.0.0.1:8789")
    c = app.test_client()
    c.get("/auth?t=" + make_token("cyc-secret-0123456789", time.time()))
    h = {"X-CSRF": c.get("/api/me").get_json()["csrf"]}
    st = c.get("/api/status").get_json()
    check(st["cycle"] == "h1" and st["hold"]["count"] == 1 and st["hold"]["next_run"] and "fix_cap" not in st["receiver"], "현황: 주기 · 대기열 · 다음 실행, 수정 상한 항목 없음")
    r = c.post("/api/mode", json={"mode": "semi"}, headers=h)
    check(r.status_code == 409 and r.get_json()["needs_queue"] and r.get_json()["count"] == 1, "API: 대기열이 있으면 409 + 건수")
    r = c.post("/api/mode", json={"mode": "semi", "queue": "discard"}, headers=h)
    check(r.status_code == 200 and r.get_json()["mode"] == "semi", "API: 버리고 변경")
    r = c.post("/api/cycle", json={"cycle": "h3"}, headers=h)
    check(r.status_code == 200 and c.get("/api/policy").get_json()["cycle"] == "h3", "API: 주기 변경")
    check(c.post("/api/cycle", json={"cycle": "x"}, headers=h).status_code == 400, "API: 잘못된 주기는 400")
    check(c.post("/api/cycle", json={"cycle": "h1"}).status_code == 403, "API: CSRF 없는 주기 변경은 403")

    html = (Path(__file__).parent / "web_static" / "index.html").read_text(encoding="utf-8")
    check(all(x in html for x in ('id="cyc-btns"', 'id="dlgov"', "/api/cycle", "needs_queue", "'process'", "'discard'")), "화면: 동작 주기 카드 · 대기열 팝업")

    # 9-2) 수동 분석 · 수정 버튼 — 정책이 '끔'인 WARN 을 사람이 눌러 처리
    pol.set_mode("auto")
    rx.change_cycle("event")
    pol.save({"WARN": {"action": "off", "record": True}})
    w = env("WARN", "수동 대상 경고", "src.backend.cyc_manual")
    n5 = ncalls()
    feed(w)
    check(ncalls() == n5, "정책 '끔'인 WARN 은 분석하지 않음")
    sg = signature(w)
    ok, msg = rx.manual_run(sg, False)
    for _ in range(100):
        if not rx.manual_busy():
            break
        time.sleep(0.1)
    check(ok and ncalls() == n5 + 1 and not rx.manual_busy(), "수동 분석: 정책과 무관하게 지금 분석 1회")
    ok, msg = rx.manual_run("없는-시그니처", False)
    check(not ok, "원본 기록이 없는 시그니처는 거부: " + msg)
    pol.set_mode("off")
    check(not rx.manual_run(sg, False)[0], "끔 모드에서는 수동 실행도 거부")
    pol.set_mode("auto")
    r = c.post("/api/manual", json={"sig": sg, "fix": False}, headers=h)
    check(r.status_code == 200 and r.get_json()["ok"], "API: 수동 분석 요청")
    for _ in range(100):
        if not rx.manual_busy():
            break
        time.sleep(0.1)
    check(c.post("/api/manual", json={"sig": "../x"}, headers=h).status_code == 400, "API: 잘못된 시그니처는 400")
    check(c.post("/api/manual", json={"sig": sg}).status_code == 403, "API: CSRF 없으면 403")
    check("manualPanel" in html and "/api/manual" in html, "화면: 수동 분석 · 수정 패널")
    check(rx.saved_analysis(sg) is None, "원인 불명(unknown) 분석은 '이 분석으로 수정' 대상이 아님")
    rf = max((cfg.rx / "runs").glob("*.json"), key=lambda p_: p_.stat().st_mtime)  # 가짜 claude 는 unknown 만 내므로 확정으로 고쳐 시험
    rd = json.loads(rf.read_text(encoding="utf-8")); rd["analysis"]["verdict"] = "confirmed"
    rf.write_text(json.dumps(rd, ensure_ascii=False), encoding="utf-8")
    sa = rx.saved_analysis(sg)
    check(sa is not None and sa["analysis"]["verdict"] == "confirmed" and sg in rx.fixable_sigs(), "분석 결과가 실행 기록에 저장돼 '이 분석으로 수정' 대상이 됨")
    ok, msg = rx.manual_fix(sg)
    check(not ok and "1단계" in msg, "1단계에서는 저장된 분석으로도 수정 불가: " + msg)
    check(c.post("/api/manual_fix", json={"sig": sg}, headers=h).status_code == 409, "API: manual_fix 거부는 409")
    check(c.post("/api/manual_fix", json={"sig": "../x"}, headers=h).status_code == 400, "API: manual_fix 잘못된 시그니처 400")
    check(sg in c.get("/api/errors").get_json()["fixable"], "API: errors 응답에 fixable 포함")
    import shutil, subprocess
    if shutil.which("node"):
        import re as _re
        js = tmp / "page.js"
        js.write_text(_re.search(r"<script>(.*)</script>", html, _re.S).group(1), encoding="utf-8")
        check(subprocess.run(["node", "--check", str(js)], capture_output=True).returncode == 0, "화면: 페이지 스크립트 구문 검사(node --check)")

    # 10) 정책 초기화는 주기도 기본값으로
    pol.reset("test")
    check(pol.cycle() == "event" and pol.mode() == "auto", "정책 초기화 → 모드 자동 · 주기 이벤트마다")
    print("모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
