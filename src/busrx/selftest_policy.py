"""에러 레벨별 정책 · 실행 기록 self-test — 정책 검증/저장/반영, 수신기 동작, 관리 페이지 API (가짜 claude · 가짜 텔레그램).

    python -m src.busrx.selftest_policy
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

from src.bus import envelope as E

from .policy import Policy, defaults, validate
from .receiver import Config, Receiver
from .selftest_web import STUB, FakeTG
from .web import create_app, make_token


def env(sev, msg="정책 시험 에러", logger="src.backend.policy_test"):
    return E.build_err(kind="log", severity=sev, message=msg, source={"env": "local", "service": "runner"}, logger=logger)


def main() -> int:
    def check(c, m):
        assert c, m
        print("OK ", m)

    tmp = Path(tempfile.mkdtemp(prefix="mewpol_"))
    stub = tmp / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    stublog = tmp / "stub.log"
    # STUB 는 호출 기록이 없으므로 래퍼로 호출 횟수를 센다
    wrapper = tmp / "wrap.py"
    wrapper.write_text(f"import subprocess, sys\nopen(r'{stublog}', 'a').write('x')\nr = subprocess.run([sys.executable, r'{stub}'], input=sys.stdin.buffer.read().decode('utf-8', 'replace'), text=True, "
                       f"capture_output=True, encoding='utf-8')\nsys.stdout.write(r.stdout)\n", encoding="utf-8")

    def ncalls():
        return len(stublog.read_text()) if stublog.exists() else 0

    cfg = Config(bus_dir=tmp / "bus", claude_cmd=[sys.executable, str(wrapper)], stage=1, batch_wait_sec=0, cooldown_error=3600,
                 cooldown_critical=300, runner_dir=tmp)
    tg = FakeTG()
    rx = Receiver(cfg, tg)
    sp = rx.spool

    # 1) 기본값 = 운영자 정의
    d = defaults(cfg)
    check(d["CRITICAL"]["action"] == "fix" and d["CRITICAL"]["preset"] == "urgent" and d["CRITICAL"]["cooldown_sec"] == 300, "기본: CRITICAL = 수정 · 긴급 프리셋 · 쿨다운 5분")
    check(d["ERROR"]["action"] == "fix" and d["ERROR"]["preset"] == "standard" and d["ERROR"]["cooldown_sec"] == 3600, "기본: ERROR = 수정 · 표준 프리셋 · 쿨다운 1시간")
    check(all(d[s]["action"] == "off" and d[s]["record"] for s in ("WARN", "INFO", "DEBUG")), "기본: WARN 이하 = 끔(기록만)")

    # 2) 검증 규칙
    _, errs = validate({"WARN": {"action": "fix"}}, d)
    check(not errs and validate({"WARN": {"action": "fix"}}, d)[0]["WARN"]["action"] == "fix", "WARN 이하도 '수정까지' 허용")
    for bad in ({"ERROR": {"action": "delete"}}, {"ERROR": {"preset": "mystery"}}, {"ERROR": {"cooldown_sec": -1}},
                {"ERROR": {"cooldown_sec": "5"}}, {"ERROR": {"record": "yes"}}, {"NOPE": {"action": "off"}}, {"INFO": {"action": "mystery"}}):
        check(validate(bad, d)[1], f"잘못된 입력 거부: {json.dumps(bad, ensure_ascii=False)}")
    ok, errs = validate({"WARN": {"action": "analyze", "cooldown_sec": 60}}, d)
    check(not errs and ok["WARN"]["action"] == "analyze" and ok["ERROR"] == d["ERROR"], "정상 입력은 해당 칸만 바뀜")

    # 3) 저장 · 이력 · 재로드 · 손상 복구 · 초기화
    pol = rx.policy
    check(pol.get("ERROR")["action"] == "fix", "정책 파일이 없으면 기본값")
    new, errs = pol.save({"WARN": {"action": "analyze"}, "ERROR": {"cooldown_sec": 0}}, who="test")
    check(not errs and new["WARN"]["action"] == "analyze" and Policy(cfg.rx / "policy.json", cfg).get("ERROR")["cooldown_sec"] == 0, "저장 후 다른 인스턴스에서도 읽힘")
    hist = (cfg.rx / "policy_history.jsonl").read_text(encoding="utf-8").splitlines()
    check(len(hist) == 1 and json.loads(hist[0])["by"] == "test" and "WARN" in json.loads(hist[0])["changed"], "변경 이력(누가 · 무엇을) 기록")
    (cfg.rx / "policy.json").write_text("{깨진 json", encoding="utf-8")
    time.sleep(0.02)
    check(Policy(cfg.rx / "policy.json", cfg).get("ERROR") == d["ERROR"], "정책 파일이 손상되면 기본값으로 안전하게 복구")
    pol.reset("test")
    check(not (cfg.rx / "policy.json").exists() and pol.get("WARN")["action"] == "off", "초기화하면 기본값")

    # 4) 수신기 동작: WARN 기본 = 호출 없이 기록만
    def feed(e):
        sp.put("err/inbox", f"{e['ts'].replace('-', '').replace(':', '')}_{e['id']}", e)
        rx.step()

    feed(env("WARN", "경고 하나", "src.collector.a"))
    check(ncalls() == 0 and any(json.loads(x)["severity"] == "WARN" for x in (cfg.rx / "log.jsonl").read_text(encoding="utf-8").splitlines()),
          "WARN(끔): claude 호출 없이 기록만")
    # WARN → 분석만
    pol.save({"WARN": {"action": "analyze", "cooldown_sec": 0}})
    feed(env("WARN", "경고 둘", "src.collector.b"))
    check(ncalls() == 1 and rx.spool.count("report/inbox") == 1, "WARN(분석만): 분석 1회 + 보고서 생성")
    run = [json.loads(p.read_text(encoding="utf-8")) for p in (cfg.rx / "runs").glob("*.json")][-1]
    check(run["action"] == "analyze" and run["steps"][0]["id"] == "analysis" and run["steps"][0]["status"] == "ok" and run["severity"] == "WARN",
          "실행 기록(runs): 정책 동작 · 분석 단계 · 심각도")
    # ERROR → 끔: 호출 없음 + 기록 / record=false 면 기록도 안 함
    pol.save({"ERROR": {"action": "off"}})
    n = ncalls()
    feed(env("ERROR", "에러(끔)", "src.backend.c"))
    check(ncalls() == n, "ERROR(끔): 분석하지 않음")
    pol.save({"ERROR": {"record": False}})
    lines = len((cfg.rx / "log.jsonl").read_text(encoding="utf-8").splitlines())
    feed(env("ERROR", "에러(기록 안 함)", "src.backend.d"))
    check(len((cfg.rx / "log.jsonl").read_text(encoding="utf-8").splitlines()) == lines, "record=false 면 기록도 남기지 않음")
    # ERROR → 분석(쿨다운은 정책 값): 쿨다운 0 이면 같은 시그니처도 즉시 재분석, 3600 이면 생략
    pol.save({"ERROR": {"action": "analyze", "record": True, "cooldown_sec": 0}})
    n = ncalls()
    feed(env("ERROR", "반복 에러", "src.backend.e"))
    feed(env("ERROR", "반복 에러", "src.backend.e"))
    check(ncalls() == n + 2, "쿨다운 0: 같은 시그니처도 매번 분석")
    pol.save({"ERROR": {"cooldown_sec": 3600}})
    n = ncalls()
    feed(env("ERROR", "반복 에러2", "src.backend.f"))
    feed(env("ERROR", "반복 에러2", "src.backend.f"))
    check(ncalls() == n + 1, "쿨다운 3600: 두 번째는 생략")
    # confirmed + 분석만 → 명세서 단계는 '건너뜀'(정책) — stub 분석은 unknown 이라 직접 확인은 steps 구조로
    check(all("id" in s and "status" in s for p in (cfg.rx / "runs").glob("*.json") for s in json.loads(p.read_text(encoding="utf-8"))["steps"]),
          "모든 실행 기록의 단계가 id/status 를 가짐")

    # 5) 관리 페이지 API
    app = create_app(rx, cfg, tg, "pol-secret-0123456789", "http://127.0.0.1:8789")
    c = app.test_client()
    check(c.get("/api/policy").status_code == 401, "미인증 /api/policy 는 401")
    c.get("/auth?t=" + make_token("pol-secret-0123456789", time.time()))
    csrf = c.get("/api/me").get_json()["csrf"]
    h = {"X-CSRF": csrf}
    g = c.get("/api/policy").get_json()
    check(g["severities"][0] == "CRITICAL" and "fix" in g["actions"] and "urgent" in g["presets"] and g["policy"]["WARN"]["action"] == "analyze", "정책 조회: 심각도 · 동작 · 프리셋 · 현재값")
    check(c.post("/api/policy", json={"policy": {}}).status_code == 403, "CSRF 없는 정책 저장은 403")
    r = c.post("/api/policy", json={"policy": {"CRITICAL": {"preset": "standard", "cooldown_sec": 120}}}, headers=h)
    check(r.status_code == 200 and rx.policy.get("CRITICAL")["preset"] == "standard" and rx.policy.get("CRITICAL")["cooldown_sec"] == 120, "정책 저장 → 수신기에 즉시 반영")
    r = c.post("/api/policy", json={"policy": {"WARN": {"action": "delete"}}}, headers=h)
    check(r.status_code == 400 and r.get_json()["errors"] and rx.policy.get("WARN")["action"] == "analyze", "검증 실패는 400 + 저장 안 됨")
    r = c.post("/api/policy", json={"policy": {"WARN": {"action": "fix", "preset": "standard"}}}, headers=h)
    check(r.status_code == 200 and rx.policy.get("WARN")["action"] == "fix", "WARN 수정까지 저장 가능")
    c.post("/api/policy", json={"policy": {"WARN": {"action": "analyze"}}}, headers=h)
    r = c.post("/api/policy", json={"reset": True}, headers=h)
    check(r.get_json()["policy"]["CRITICAL"]["preset"] == "urgent" and r.get_json()["policy"]["WARN"]["action"] == "off", "기본값으로 되돌리기")
    runs = c.get("/api/runs").get_json()["runs"]
    check(len(runs) >= 3 and all("steps" in x for x in runs), "실행 기록 API")
    st = c.get("/api/status").get_json()
    check(st["policy"]["ERROR"]["action"] == "fix", "현황에 정책 포함")
    html = (Path(__file__).parent / "web_static" / "index.html").read_text(encoding="utf-8")
    check('id="pol-body"' in html and 'id="run-list"' in html and "에러 레벨별 자동 대응" in html, "화면: 정책 표 · 파이프라인 도식 영역")
    print("모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
