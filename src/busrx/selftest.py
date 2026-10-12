"""수신기 self-test — 가짜 claude(스텁)와 가짜 텔레그램으로 동작을 확인한다 (네트워크 · 모델 호출 없음).

    python -m src.busrx.selftest
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from src.bus import envelope as E

from .receiver import STAGE_PATCH_NOTE, Config, Receiver, git_head, signature

STUB = r'''
import json, os, sys
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
log = {"argv": sys.argv[1:], "cwd": os.getcwd(), "env_has_secret": any(k in os.environ for k in
       ("GROQ_API_KEY", "YOUTUBE_API_KEY", "TELEGRAM_BOT_TOKEN", "GITHUB_TOKEN")),
       "has_dotenv": os.path.exists(".env.local"), "has_git": os.path.exists(".git"),
       "prompt_len": len(prompt)}
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(log) + "\n")
if os.environ.get("STUB_FAIL"):
    sys.stderr.write("boom"); sys.exit(1)
big = "x" * int(os.environ.get("STUB_BIG", "0"))
print(json.dumps({"structured_output": {"verdict": "confirmed", "summary": "스텁 분석 한 줄",
      "cause": "스텁 원인" + big, "evidence": ["src/x.py:1 — 스텁"], "proposed_action": "스텁 제안"},
      "total_cost_usd": 0.01, "is_error": False}))
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


def env(msg="boom", sev="ERROR", logger="src.backend.handlers", tb="", **kw):
    e = E.build_err(kind="log", severity=sev, message=msg, source={"env": "local", "service": "runner", "commit": "abc1234"},
                    logger=logger, traceback=tb, **kw)
    return e


def main() -> int:
    def check(c, m):
        assert c, m
        print("OK ", m)

    tmp = Path(tempfile.mkdtemp(prefix="mewrx_"))
    bus = tmp / "bus"
    stub = tmp / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    os.environ["STUB_LOG"] = str(tmp / "stub.log")
    os.environ["GROQ_API_KEY"] = "must-not-leak-1234567890"
    clock = [1_800_000_000.0]
    cfg = Config(bus_dir=bus, stage=1, claude_cmd=[sys.executable, str(stub)], cooldown_error=3600, cooldown_critical=300,
                 daily_cap=3, batch_wait_sec=0,
                 extra_env={"STUB_LOG": str(tmp / "stub.log")})
    tg = FakeTG()
    rx = Receiver(cfg, tg, now=lambda: clock[0])
    sp = rx.spool
    head = git_head(cfg.repo)

    def put(e, name=None):
        sp.put("err/inbox", name or f"{e['ts'].replace('-', '').replace(':', '')}_{e['id']}", e)

    def calls():
        p = Path(os.environ["STUB_LOG"])
        return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []

    # 1) ERROR → 분석 → 보고 (로그 · 패치 1줄 · 커밋 이전→이후 표시)
    e1 = env("YouTube API error: 403 key=SECRETKEY99", tb="Traceback...\nRuntimeError: YouTube API error: 403")
    put(e1)
    check(rx.step() == 1, "ERROR 봉투 1건 처리")
    def rep_text():  # 텔레그램으로 간 마지막 보고: 캡션 + 첨부 파일 내용
        f = tg.files[-1]
        return f[2] + "\n" + f[1]

    m = rep_text()
    check("403" in m and "SECRETKEY99" not in m, "텔레그램에 수신 로그 표시 + 비밀값 마스킹")
    check(STAGE_PATCH_NOTE in m, "텔레그램에 패치 1줄 요약(1단계: 패치 없음) 표시")
    check(f"커밋: {head} → {head} (변경 없음)" in m, "텔레그램에 커밋 이전→이후 표시")
    check("스텁 분석 한 줄" in m and "원인 확정" in m, "분석 판정 · 한 줄 요약 표시")
    check("세션(5시간)**: 4" in m and "남음 5" in m and "초기화 15:00 KST" in m and "주간(7일)**: 54% 사용 · 남음 46%" in m,
          "사용량: 세션(5시간) 사용·남음·초기화 + 주간 사용·남음 표시")
    check("이번 처리 +" in m, "사용량: 이번 처리에서 쓴 세션 사용률(%p) 표시")
    rep = [json.loads(p.read_text(encoding="utf-8")) for p in sp.list("report/inbox")]
    check(len(rep) == 1 and rep[0]["commit_before"] == head and rep[0]["verdict"] == "confirmed", "report/inbox 에 mew.report/1 기록")
    check(sp.count("err/inbox") == 0 and sp.count("err/done") == 1, "처리된 봉투는 done 으로 이동")

    # 2) claude 호출 방식 — 읽기 전용 도구 · 환경 격리 · 스냅샷
    c = calls()[-1]
    a = c["argv"]
    check("-p" in a and a[a.index("--tools") + 1] == "Read,Grep,Glob", "claude 는 Read/Grep/Glob 만 허용(--tools)")
    check("--max-budget-usd" in a and "--no-session-persistence" in a and "--json-schema" in a, "비용 상한 · 무세션 · 스키마 지정")
    check(not c["env_has_secret"], "claude 서브프로세스에 비밀 환경 변수 비전달")
    check(not c["has_dotenv"] and not c["has_git"], "작업 폴더는 .env/.git 없는 스냅샷")

    # 3) 같은 시그니처 쿨다운 · 중복 id
    n = len(calls())
    put(env("YouTube API error: 403 key=OTHER", tb="Traceback...\nRuntimeError: YouTube API error: 403"))
    rx.step()
    check(len(calls()) == n, "쿨다운 안의 같은 시그니처는 재호출 안 함")
    put(e1, name="dup_" + e1["id"])
    rx.step()
    check(len(calls()) == n and sp.count("err/inbox") == 0, "같은 id 는 멱등 처리")

    # 4) WARN 은 기록만
    put(env("rss 경고", sev="WARN", logger="src.collector.rss"))
    rx.step()
    check(len(calls()) == n and (bus / "rx" / "log.jsonl").exists(), "WARN 은 호출 없이 log.jsonl 기록")

    # 5) 잘못된 봉투 → dead
    bad = env("x")
    bad["severity"] = "WARNING"
    put(bad, name="bad")
    rx.step()
    check(sp.count("err/dead") == 1 and list((bus / "err" / "dead").glob("*.why.txt")), "스키마 위반은 dead + 사유 파일")

    # 6) 긴 보고는 파일로
    cfg.extra_env["STUB_BIG"] = "4000"
    put(env("다른 에러 하나", logger="src.backend.other"))
    rx.step()
    check(len(tg.files[-1][1]) > 4000 and STAGE_PATCH_NOTE in tg.files[-1][2] and f"커밋: {head} → {head}" in tg.files[-1][2]
          and len(tg.files[-1][2]) < 900, "긴 보고도 텔레그램에는 짧은 캡션(패치 · 커밋) + 전체 마크다운 파일")
    cfg.extra_env.pop("STUB_BIG")

    # 7) claude 실패 → 분석 실패 보고(원인 불명)
    cfg.extra_env["STUB_FAIL"] = "1"
    put(env("또 다른 에러", logger="src.backend.third"))
    rx.step()
    check("분석 실패" in rep_text() and "원인 불명" in rep_text(), "claude 실패 시 '분석 실패/원인 불명'으로 보고")
    cfg.extra_env.pop("STUB_FAIL")

    # 8) 일일 상한(3회) 도달
    before = len(tg.msgs)
    put(env("네 번째 에러", logger="src.backend.fourth"))
    rx.step()
    check("일일 상한" in tg.msgs[-1] and len(tg.msgs) == before + 1, "일일 상한 도달 시 안내 1회만")

    # 9) PAUSE · 쿨다운 해제 후
    clock[0] += 86400
    (bus / "rx" / "PAUSE").write_text("", encoding="utf-8")
    n2 = len(calls())
    put(env("정지 중 에러", logger="src.backend.paused"))
    rx.step()
    check(len(calls()) == n2, "PAUSE 파일이 있으면 분석 안 함")
    (bus / "rx" / "PAUSE").unlink()

    # 10) 발신기 소실 감시
    (bus / "hb").mkdir(exist_ok=True)
    old = E.iso(clock[0] - 300)
    (bus / "hb" / "publisher.json").write_text(json.dumps({"schema": "mew.hb/1", "role": "publisher", "ts": old, "pid": 1}), encoding="utf-8")
    rx._last_hb = 0
    rx.heartbeat()
    check("발신기 소실" in tg.msgs[-1], "발신기 hb 가 120초 넘게 멈추면 CRITICAL 알림")
    (bus / "hb" / "publisher.json").write_text(json.dumps({"schema": "mew.hb/1", "role": "publisher", "ts": E.iso(clock[0]), "pid": 1}), encoding="utf-8")
    rx._last_hb = 0
    rx.heartbeat()
    check("발신기 복구" in tg.msgs[-1] and (bus / "hb" / "receiver.json").exists(), "복구 알림 + receiver hb 기록")

    # 11) 재시작 복구
    p = sp.put("err/processing", "stuck_" + E.new_id(), env("stuck"))
    check(rx.recover() == 1 and sp.count("err/inbox") == 1, "processing 에 남은 봉투를 inbox 로 복구")

    # 12) 시그니처 안정성
    s1 = signature(env("Failed to fetch RSS for channel UC" + "a" * 22 + ": 404 try 1", sev="WARN", logger="rss"))
    s2 = signature(env("Failed to fetch RSS for channel UC" + "b" * 22 + ": 404 try 99", sev="WARN", logger="rss"))
    check(s1 == s2, "숫자 · 채널 ID 만 다른 메시지는 같은 시그니처")
    print("모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
