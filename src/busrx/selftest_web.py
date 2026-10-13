"""자동제어 관리 페이지 self-test — Flask 테스트 클라이언트 + 가짜 claude · 가짜 텔레그램 (네트워크 · 모델 호출 없음).

    python -m src.busrx.selftest_web
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

from src.bus import envelope as E
from src.bus.conform import validate

from .receiver import Config, Receiver
from .web import create_app, make_token, verify_token

STUB = r'''
import json, os, sys
prompt = sys.stdin.read()
print(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {
    "five_hour": {"utilization": 0.46, "resetsAt": 1791784800}, "seven_day": {"utilization": 0.54, "resetsAt": 1791799200}}}}))
if "[[PURPOSE:analysis]]" in prompt:
    print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.01, "result": "", "structured_output": {
        "verdict": "unknown", "summary": "스텁 요약", "cause": "스텁 원인", "evidence": ["x.py:1 — 스텁"], "proposed_action": "확인"}}))
else:
    print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.001, "result": "ok"}))
'''


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


def main() -> int:
    def check(c, m):
        assert c, m
        print("OK ", m)

    tmp = Path(tempfile.mkdtemp(prefix="mewweb_"))
    bus = tmp / "bus"
    stub = tmp / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    clock = [1_800_000_000.0]
    cfg = Config(bus_dir=bus, claude_cmd=[sys.executable, str(stub)], stage=1, batch_wait_sec=0, cooldown_error=0,
                 runner_dir=tmp, usage_probe_min_sec=120)
    tg = FakeTG()
    rx = Receiver(cfg, tg, now=lambda: clock[0])
    secret = "web-test-secret-0123456789"
    app = create_app(rx, cfg, tg, secret, "http://127.0.0.1:8789", now=lambda: clock[0])
    c = app.test_client()

    # 1) 인증 전 접근 차단
    check(c.get("/api/status").status_code == 401, "미인증 /api/status 는 401")
    r = c.get("/")
    check(r.status_code == 302 and r.headers["Location"].endswith("/login"), "미인증 / 는 /login 으로 이동")
    check(c.get("/login").status_code == 200, "/login 페이지 제공")

    # 2) 텔레그램 일회용 링크 로그인
    r = c.post("/login/request")
    check(r.status_code == 200 and "/auth?t=" in tg.msgs[-1], "로그인 링크가 텔레그램으로 전송됨")
    check(c.post("/login/request").status_code == 429, "링크 요청은 20초 간격 제한")
    tok = re.search(r"/auth\?t=(\S+)", tg.msgs[-1]).group(1)
    check(verify_token(secret, tok, clock[0]) is not None and verify_token("다른키", tok, clock[0]) is None, "토큰 서명 검증")
    check(c.get("/auth?t=" + tok[:-3] + "xxx").status_code == 400, "변조된 토큰 거부")
    check(verify_token(secret, make_token(secret, clock[0] - 1000), clock[0]) is None, "만료된 토큰 거부")
    r = c.get("/auth?t=" + tok)
    check(r.status_code == 302 and "rx_sess=" in r.headers.get("Set-Cookie", "") and "HttpOnly" in r.headers["Set-Cookie"], "유효한 링크로 로그인 + HttpOnly 쿠키")
    check(c.get("/auth?t=" + tok).status_code == 400, "링크는 1회용")

    # 3) 세션 · CSRF
    csrf = c.get("/api/me").get_json()["csrf"]
    check(c.post("/api/rx/pause", json={"on": True}).status_code == 403, "CSRF 헤더 없는 쓰기는 403")
    h = {"X-CSRF": csrf}

    # 4) 현황
    st = c.get("/api/status").get_json()
    check(st["stage"] == 1 and st["models"]["code"] == "claude-haiku-5-5" and "queue" in st and st["publisher"]["alive"] is False,
          "현황: 단계 · 모델 · 큐 · 발신기 생존(신호 없음) 포함")
    check(c.get("/api/me").get_json()["csrf"] == csrf, "세션 유지")

    # 5) 에러 목록 · 보고서 (실제 수신기 경로로 한 건 처리)
    env = E.build_err(kind="log", severity="ERROR", message="웹 시험 에러 key=ABCDEF123456", source={"env": "local", "service": "runner"},
                      logger="src.backend.web_test")
    rx.spool.put("err/inbox", f"{env['ts'].replace('-', '').replace(':', '')}_{env['id']}", env)
    check(rx.step() == 1, "수신기가 에러 1건 처리")
    errs = c.get("/api/errors").get_json()["errors"]
    check(len(errs) == 1 and errs[0]["sev"] == "ERROR" and errs[0]["verdict"] == "unknown" and errs[0]["report"].endswith(".md")
          and "ABCDEF123456" not in errs[0]["msg"], "에러 목록: 심각도 · 판정 · 보고서 연결 · 비밀값 마스킹")
    check(len(c.get("/api/errors?sev=WARN").get_json()["errors"]) == 0, "심각도 필터")
    check(any(x.get("note") == "분석함" for x in c.get("/api/errors?log=1").get_json()["log"]), "기록 보기: 분석한 건도 log 에 남음")
    reps = c.get("/api/reports").get_json()["reports"]
    check(len(reps) == 1, "보고서 목록")
    body = c.get("/api/report/" + reps[0]["name"]).get_json()
    check("원인 불명" in body["text"] and "## 4. 구독 사용량" in body["text"], "보고서 본문 조회(마크다운)")
    check(c.get("/api/report/..%5Cstate.json").status_code in (400, 404) and c.get("/api/report/x.md").status_code == 400, "보고서 경로 이탈 차단")

    # 6) 수정 이력 (수정 필드가 있는 report 봉투)
    rep = {"schema": "mew.report/1", "id": E.new_id(), "ts": "2026-10-12T06:00:00Z", "signature": "sig-x", "verdict": "confirmed", "summary": "s",
           "patch_summary": "calc 수정", "fix_status": "applied", "fix_branch": "auto/sig-x-1", "fix_version": "v4.3.1", "guard_ok": True,
           "applied": True, "restarted": True, "commit_before": "aaaa111", "commit_after": "bbbb222", "lines_added": 3, "lines_deleted": 1,
           "files_changed": [{"path": "src/backend/calc.py", "added": 3, "deleted": 1}]}
    check(not validate(rep), "수정 이력용 report 봉투가 스키마에 적합")
    rx.spool.put("report/inbox", "20261012T060000Z_x", rep)
    fx = c.get("/api/fixes").get_json()["fixes"]
    check(len(fx) == 1 and fx[0]["fix_status"] == "applied" and fx[0]["lines_added"] == 3 and fx[0]["report"] == "20261012T060000Z_sig-x.md",
          "수정 이력: 파일별 +/− · 합계 · 커밋 전후 · 보고서 이름")

    # 7) 구독 사용량: 조회 · 최소 간격
    u0 = c.get("/api/usage").get_json()["usage"]
    check(u0 is not None and abs(u0["five"] - 0.46) < 1e-9, "분석 직후 사용량이 저장되어 표시됨(세션 46%)")
    r = c.post("/api/usage/refresh", headers=h).get_json()
    check("재사용" in r["msg"] and r["usage"]["seven"] == 0.54, "최소 간격 안에서는 새 호출 없이 재사용")
    clock[0] += 3600
    import time as _t
    rx.state["usage_now"]["t"] = _t.time() - 3600  # 실제 시계 기준 만료 (probe 는 time.time 사용)
    r = c.post("/api/usage/refresh", headers=h).get_json()
    check(r["msg"] == "조회 완료" and r["usage"]["five"] == 0.46, "간격이 지나면 소형 호출로 새로 조회")

    # 8) 제어: 수신기 정지 · 발신기 제어 봉투
    check(c.post("/api/rx/pause", json={"on": True}, headers=h).get_json()["rx_paused"] is True and (bus / "rx" / "PAUSE").exists(), "수신기 분석 정지(PAUSE 파일)")
    check(c.get("/api/status").get_json()["rx_paused"] is True, "현황에 정지 반영")
    check(c.post("/api/rx/pause", json={"on": False}, headers=h).get_json()["rx_paused"] is False, "수신기 분석 재개")
    r = c.post("/api/pub/level", json={"level": "DEBUG", "ttl_sec": 600}, headers=h)
    ctls = [json.loads(p.read_text(encoding="utf-8")) for p in rx.spool.list("ctl/inbox")]
    check(r.status_code == 200 and ctls[-1]["cmd"] == "set_level" and ctls[-1]["args"] == {"level": "DEBUG", "ttl_sec": 600}
          and not validate(ctls[-1]), "발신 레벨 변경 → 적합한 mew.ctl/1 봉투가 ctl/inbox 에 기록")
    check(c.post("/api/pub/level", json={"level": "CRITICAL"}, headers=h).status_code == 400, "허용되지 않은 레벨은 거부")
    r = c.post("/api/pub/pause", json={"on": True, "ttl_sec": 900}, headers=h)
    ctls = [json.loads(p.read_text(encoding="utf-8")) for p in rx.spool.list("ctl/inbox")]
    check(r.status_code == 200 and ctls[-1]["cmd"] == "pause" and ctls[-1]["args"] == {"ttl_sec": 900}, "발신 정지(시간 제한) 제어 봉투")
    check(c.get("/api/ctl").get_json()["pending"].count("set_level") == 1, "처리 대기 중인 제어 봉투 표시")

    # 9) 화면 파일 점검
    html = (Path(__file__).parent / "web_static" / "index.html").read_text(encoding="utf-8")
    check(all(x in html for x in ('data-t="overview"', 'data-t="control"', 'data-t="settings"', 'id="usage"', 'id="ctl-list"', 'id="hc-grid"')),
          "화면: Overview · Control · Settings 탭과 상단 사용량 영역")
    check("세션(5시간)" in html and "주간(7일)" in html, "화면: 세션/주간 사용량 표시 문구")
    check(c.get("/").status_code == 200 and "Content-Security-Policy" in c.get("/").headers, "인증 후 / 제공 + CSP 헤더")
    print("모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
