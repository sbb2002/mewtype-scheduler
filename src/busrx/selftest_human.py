"""'사람 조치 필요' 처리 · 새 외부 호스트/환경변수 가드 self-test (가짜 claude · 가짜 텔레그램).

    python -m src.busrx.selftest_human
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from src.bus import envelope as E

from . import guard
from .receiver import RESULT_SCHEMA, SYSTEM_RULES, Config, Receiver, signature
from .selftest_web import FakeTG
from .web import create_app, make_token

# 분석 호출에는 needs_human=true(외부 서비스 인증 문제)를, 그 밖(명세 · 구현 · 검증)에는 '호출됨'만 센다
STUB = r'''
import json, sys
prompt = sys.stdin.read()
print(json.dumps({"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {
    "five_hour": {"utilization": 0.1, "resetsAt": 1791784800}, "seven_day": {"utilization": 0.1, "resetsAt": 1791799200}}}}))
if "[[PURPOSE:analysis]]" in prompt:
    print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.01, "result": "", "structured_output": {
        "verdict": "confirmed", "summary": "외부 API 가 401(키 무효)을 돌려줌", "cause": "공급자가 인증을 거부했다 — 코드 버그 아님",
        "evidence": ["src/backend/llm.py:1030 — HTTP 4xx 는 재시도 없이 None"], "proposed_action": "키를 갱신하거나 요금제/공급자를 사람이 정한다",
        "impact": "번역이 원문으로만 나간다(지속)", "needs_human": True, "human_action": "공급자 대시보드에서 키 상태 · 요금제를 확인하고 키를 교체하거나 공급자를 정하세요"}}))
else:
    print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.001, "result": "ok"}))
'''


def env(sev, msg, logger):
    return E.build_err(kind="log", severity=sev, message=msg, source={"env": "local", "service": "runner"}, logger=logger)


def main() -> int:
    def check(c, m):
        assert c, m
        print("OK ", m)

    # ── 가드: 새 외부 호스트 · 환경변수 이름 ──
    kh, ke = {"api.groq.com", "www.googleapis.com"}, {"GROQ_API_KEY", "YOUTUBE_API_KEY"}
    d = ('+++ b/src/backend/llm.py\n+    url = "https://openrouter.ai/api/v1/chat/completions"\n'
         '+    key = os.environ.get("OPENROUTER_API_KEY")\n+    # https://docs.openrouter.ai/ 참고\n'
         '+    ok = "https://api.groq.com/openai/v1/chat/completions"\n+    k2 = os.getenv("GROQ_API_KEY")\n'
         '+    ex = "https://example.com/x"\n')
    v = guard.external_additions(d, kh, ke)
    check(len(v) == 2 and any("openrouter.ai" in x for x in v) and any("OPENROUTER_API_KEY" in x for x in v),
          "가드: 없던 외부 호스트 · 환경변수 이름만 걸리고 기존 것 · 주석 · 예시 주소는 통과")
    check(guard.external_additions('+    x = 1\n+    log.info("백오프 소진")\n', kh, ke) == [], "가드: 일반 변경은 통과")
    hosts, envs = guard.known_externals(Path(__file__).resolve().parents[2])
    check("api.groq.com" in hosts and "GROQ_API_KEY" in envs, "가드: 기준 코드에서 기존 외부 호스트 · 환경변수 이름을 모음")
    check(guard.CHECKED_ITEMS.endswith("새 외부 호스트/환경변수"), "가드: 보고 항목에 새 호스트/환경변수 포함")
    check(all(x in SYSTEM_RULES for x in ("needs_human", "human_action", "인증", "결제", "쿼터", "공급자를 바꾸는 코드를 제안하지 말 것"))
          and {"needs_human", "human_action"} <= set(RESULT_SCHEMA["properties"]) and "needs_human" not in RESULT_SCHEMA["required"],
          "분석 지침 · 스키마에 사람 조치 필요 규칙 포함(필수 필드는 아님)")

    # ── 수신기: needs_human 분석 → 수정 단계를 시작하지 않고 표시 · 알림 · 재분석 생략 ──
    tmp = Path(tempfile.mkdtemp(prefix="mewhuman_"))
    stub = tmp / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    log = tmp / "calls.log"
    wrapper = tmp / "wrap.py"
    wrapper.write_text(f"import subprocess, sys\nd = sys.stdin.buffer.read().decode('utf-8', 'replace')\nopen(r'{log}', 'a').write('A' if '[[PURPOSE:analysis]]' in d else 'X')\n"
                       f"r = subprocess.run([sys.executable, r'{stub}'], input=d, text=True, capture_output=True, encoding='utf-8')\nsys.stdout.write(r.stdout)\n", encoding="utf-8")
    calls = lambda: log.read_text() if log.exists() else ""  # noqa: E731
    clock = [time.mktime((2026, 10, 13, 10, 0, 0, 0, 0, 0)) - time.timezone]
    cfg = Config(bus_dir=tmp / "bus", claude_cmd=[sys.executable, str(wrapper)], stage=2, batch_wait_sec=0, cooldown_error=0, cooldown_critical=0,
                 runner_dir=tmp, daily_cap=100, human_ttl_sec=7200)
    tg = FakeTG()
    rx = Receiver(cfg, tg, now=lambda: clock[0])
    sp = rx.spool

    def feed(e):
        sp.put("err/inbox", f"{e['ts'].replace('-', '').replace(':', '')}_{e['id']}", e)
        rx.step()

    e1 = env("ERROR", "Groq 401: Invalid API Key", "src.backend.llm")
    sg = signature(e1)
    feed(e1)
    check(calls() == "A", "분석 1회만 호출 — 수정(명세 · 구현 · 검증) 단계를 시작하지 않음(stage 2 · 자동 모드)")
    hf = rx.human_flag(sg)
    check(hf and "공급자" in hf["action"] and sg in rx.human_sigs(), "사람 조치 필요 표시 + 사람이 할 일 저장")
    check(any("🙋 사람 조치 필요" in m and "조치 완료" in m for m in tg.msgs), "텔레그램에 사람 조치 필요 알림 1건")
    check(rx.proposals.pending_count() == 0, "계획안(승인 대기)도 만들지 않음")
    run = max((cfg.rx / "runs").glob("*.json"), key=lambda p: p.stat().st_mtime)
    rd = json.loads(run.read_text(encoding="utf-8"))
    check(rd["analysis"].get("needs_human") is True and any(s["id"] == "human" for s in rd["steps"]), "실행 기록에 needs_human · '사람 조치 필요' 단계 기록")
    md = (cfg.rx / "reports").glob("*.md")
    check(any("사람이 결정할 일" in p.read_text(encoding="utf-8") for p in md), "보고서에 '사람이 결정할 일' 항목")

    n_msgs = len(tg.msgs)
    clock[0] += 60
    feed(env("ERROR", "Groq 401: Invalid API Key", "src.backend.llm"))
    check(calls() == "A" and len(tg.msgs) == n_msgs, "같은 에러 재발: 재분석 · 재알림 없음(구독 사용량 보호)")
    logs = (cfg.rx / "log.jsonl").read_text(encoding="utf-8")
    check("사람 조치 필요 — 재분석 생략" in logs, "생략한 건은 로그에 남음")

    # 반자동 모드에서도 계획안을 만들지 않는다
    rx.policy.set_mode("semi")
    clock[0] += 60
    feed(env("ERROR", "Groq 401: Invalid API Key", "src.backend.llm"))
    check(calls() == "A" and rx.proposals.pending_count() == 0, "반자동 모드에서도 생략 — 계획안 없음")
    rx.policy.set_mode("auto")

    # 해제(조치 완료) 후에는 새로 분석
    ok, msg = rx.human_clear(sg)
    check(ok and rx.human_flag(sg) is None, "조치 완료: 표시 해제")
    check(not rx.human_clear(sg)[0], "이미 풀린 표시는 거부")
    clock[0] += 60
    feed(env("ERROR", "Groq 401: Invalid API Key", "src.backend.llm"))
    check(calls() == "AA" and rx.human_flag(sg), "해제 후 같은 에러 → 다시 분석하고 다시 표시")

    # TTL 만료
    clock[0] += 7300
    check(rx.human_flag(sg) is None, "표시는 TTL(여기서는 2시간) 뒤 만료")
    feed(env("ERROR", "Groq 401: Invalid API Key", "src.backend.llm"))
    check(calls() == "AAA", "만료 뒤 같은 에러 → 한 번 다시 분석")

    # 수동 분석은 막지 않는다(운영자가 직접 누른 것)
    ok, _ = rx.manual_run(sg, False)
    for _ in range(100):
        if not rx.manual_busy():
            break
        time.sleep(0.1)
    check(ok and calls().count("A") == 4, "운영자가 누른 수동 분석은 표시 중에도 실행")

    # ── 관리 페이지 ──
    app = create_app(rx, cfg, tg, "human-secret-0123456789", "http://127.0.0.1:8789")
    c = app.test_client()
    c.get("/auth?t=" + make_token("human-secret-0123456789", time.time()))
    h = {"X-CSRF": c.get("/api/me").get_json()["csrf"]}
    errs = c.get("/api/errors").get_json()["errors"]
    row = next(x for x in errs if x["sig"] == sg)
    check(row.get("human") and row["human"]["action"], "API: /api/errors 행에 human 정보")
    check(sg in c.get("/api/status").get_json()["human"], "API: /api/status 에 사람 조치 필요 목록")
    check(c.post("/api/human_clear", json={"sig": sg}).status_code == 403, "API: CSRF 없으면 403")
    check(c.post("/api/human_clear", json={"sig": "../x"}, headers=h).status_code == 400, "API: 잘못된 시그니처 400")
    r = c.post("/api/human_clear", json={"sig": sg}, headers=h)
    check(r.status_code == 200 and rx.human_flag(sg) is None, "API: 조치 완료")
    check(c.post("/api/human_clear", json={"sig": sg}, headers=h).status_code == 409, "API: 이미 풀린 표시는 409")
    html = (Path(__file__).parent / "web_static" / "index.html").read_text(encoding="utf-8")
    check(all(x in html for x in ("humanPanel", "/api/human_clear", "사람 조치 필요", "__human")), "화면: 사람 조치 필요 패널 · 필터 · 조치 완료 버튼")
    if shutil.which("node"):
        js = tmp / "page.js"
        js.write_text(re.search(r"<script>(.*)</script>", html, re.S).group(1), encoding="utf-8")
        check(subprocess.run(["node", "--check", str(js)], capture_output=True).returncode == 0, "화면: 페이지 스크립트 구문 검사")
    print("모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
