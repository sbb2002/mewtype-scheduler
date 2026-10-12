"""수신기 전용 텔레그램 봇 self-test — 가짜 텔레그램 서버(세션) + 가짜 claude (네트워크 · 모델 호출 없음).

    python -m src.busrx.selftest_bot
"""
from __future__ import annotations

import re
import sys
import tempfile
import time
from pathlib import Path

from .bot import BotCommands, BotPoller
from .receiver import Config, Receiver
from .selftest_web import STUB, FakeTG
from .web import verify_token

CHAT = "424242"


class FakeSession:
    """requests.Session 흉내 — getWebhookInfo / getUpdates 응답을 큐에서 꺼내 준다."""

    def __init__(self, webhook_url="", updates=None):
        self.webhook_url, self.updates, self.calls = webhook_url, list(updates or []), []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url.split("/")[-1], dict(params or {})))

        class R:
            def __init__(s, d):
                s.d = d

            def json(s):
                return s.d

        if url.endswith("getWebhookInfo"):
            return R({"ok": True, "result": {"url": self.webhook_url}})
        if url.endswith("getUpdates"):
            out, self.updates = self.updates, []
            return R({"ok": True, "result": out})
        return R({"ok": False})


def msg(text, chat=CHAT, uid=1, ctype="private"):
    return {"update_id": uid, "message": {"text": text, "chat": {"id": int(chat), "type": ctype}}}


def main() -> int:
    def check(c, m):
        assert c, m
        print("OK ", m)

    tmp = Path(tempfile.mkdtemp(prefix="mewbot_"))
    stub = tmp / "stub.py"
    stub.write_text(STUB, encoding="utf-8")
    cfg = Config(bus_dir=tmp / "bus", claude_cmd=[sys.executable, str(stub)], stage=1, runner_dir=tmp, usage_probe_min_sec=120)
    tg = FakeTG()
    rx = Receiver(cfg, tg)
    secret = "bot-test-secret-0123456789"
    h = BotCommands(rx, cfg, tg, {"secret": secret, "base": "http://100.1.2.3:8789"}, CHAT)

    # 1) /ctl: 허용된 채팅 → 로그인 링크
    check(h.handle(msg("/ctl")) == "/ctl", "/ctl 처리")
    tok = re.search(r"/auth\?t=(\S+)", tg.msgs[-1]).group(1)
    check(tg.msgs[-1].count("http://100.1.2.3:8789/auth?t=") == 1 and verify_token(secret, tok, time.time()) is not None,
          "/ctl: 관리 페이지 로그인 링크(서명 유효, 5분 · 1회용 안내)")
    check("5분" in tg.msgs[-1] and "1회" in tg.msgs[-1], "/ctl: 유효 시간 안내")

    # 2) 허용되지 않은 채팅 · 그룹 · 일반 텍스트는 무시(응답 없음)
    n = len(tg.msgs)
    check(h.handle(msg("/ctl", chat="999")) is None and len(tg.msgs) == n, "다른 chat id 의 명령은 무응답")
    check(h.handle(msg("/ctl", ctype="group")) is None and len(tg.msgs) == n, "그룹 대화의 명령은 무응답")
    check(h.handle(msg("안녕")) is None and len(tg.msgs) == n, "명령이 아닌 텍스트는 무시")
    check(h.handle(msg("/ctl@mew_autofix_bot")) == "/ctl", "봇 이름이 붙은 명령(/ctl@봇)도 인식")

    # 3) /auto 현황 · /usage · 정지/재개
    h.handle(msg("/auto"))
    m = tg.msgs[-1]
    check("자동제어 현황" in m and "1단계" in m and "수신기 분석: ▶ 동작 중" in m and "오늘 분석 0/20" in m, "/auto: 단계 · 분석 상태 · 오늘 호출")
    check("사용량: 아직 측정값 없음" in m, "/auto: 측정 전에는 안내")
    h.handle(msg("/usage"))
    m = tg.msgs[-1]
    check("세션(5시간): 46% 사용 · 남음 54%" in m and "주간(7일): 54% 사용 · 남음 46%" in m, "/usage: 세션 · 주간 사용량 조회")
    h.handle(msg("/auto"))
    check("세션(5시간): 46%" in tg.msgs[-1], "/auto: 조회한 사용량이 반영됨")
    h.handle(msg("/autopause"))
    check((cfg.bus_dir / "rx" / "PAUSE").exists() and "정지" in tg.msgs[-1], "/autopause: PAUSE 파일 생성")
    h.handle(msg("/auto"))
    check("⏸ 정지됨" in tg.msgs[-1], "/auto: 정지 상태 표시")
    h.handle(msg("/autoresume"))
    check(not (cfg.bus_dir / "rx" / "PAUSE").exists() and "재개" in tg.msgs[-1], "/autoresume: 재개")
    h.handle(msg("/help"))
    check("/ctl" in tg.msgs[-1] and "/autopause" in tg.msgs[-1], "/help 명령 목록")
    h.handle(msg("/모르는명령"))
    check("알 수 없는 명령" in tg.msgs[-1], "알 수 없는 명령 안내")
    h2 = BotCommands(rx, cfg, tg, None, CHAT)
    h2.handle(msg("/ctl"))
    check("꺼져 있습니다" in tg.msgs[-1], "관리 페이지가 꺼져 있으면 /ctl 이 사유 안내")

    # 4) 폴러: 오프셋 · 처리 · webhook 안전장치
    sess = FakeSession(updates=[msg("/help", uid=10), msg("/auto", uid=11)])
    p = BotPoller("12345678:ABCDEFGHIJKLMNOPQRSTUVWXYZ012345678", h, tmp / "off.txt", session=sess, poll_timeout=1)
    check(p.poll_once() == 2 and (tmp / "off.txt").read_text() == "12", "getUpdates 2건 처리 + 오프셋 저장(마지막 id + 1)")
    sess.updates = []
    p.poll_once()
    check(sess.calls[-1][1]["offset"] == 12 and "message" in sess.calls[-1][1]["allowed_updates"], "다음 요청은 저장된 오프셋으로, message 업데이트만")
    check(p.webhook_ok() is True, "webhook 이 없는 봇은 폴링 허용")
    bad = BotPoller("12345678:ABCDEFGHIJKLMNOPQRSTUVWXYZ012345678", h, tmp / "o2.txt", session=FakeSession(webhook_url="https://prod.run.app/telegram"))
    bad.run()
    check(bad.state == "off" and not any(c[0] == "getUpdates" or c[0] == "deleteWebhook" for c in bad.session.calls),
          "webhook 이 걸린 봇(운영 봇으로 의심)은 폴링도 deleteWebhook 도 하지 않음")
    print("모두 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
