"""수신기 전용 텔레그램 봇 — DM 명령으로 자동 대응을 다룬다 (러너 봇과 **별개의 봇**, 별개의 getUpdates 폴링).

명령(허용된 chat id 의 개인 대화에서만):
  /ctl         자동 대응 관리 페이지 로그인 링크(5분 · 1회) 전송
  /auto        현황 요약 (단계 · 정지 여부 · 발신기/러너 · 오늘 호출 · 구독 사용량)
  /autopause   수신기 분석 정지 (rx/PAUSE)
  /autoresume  수신기 분석 재개
  /usage       소형 호출로 구독 사용량을 새로 조회
  /help        명령 목록

안전: 시작 때 webhook 이 걸린 봇이면 폴링을 거부한다(운영 봇 토큰을 잘못 넣어 운영 webhook 을 지우는 사고 방지 — 이 봇은 deleteWebhook 을 호출하지 않는다).
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import requests

from .status import build_status, status_text, usage_text

log = logging.getLogger("busrx.bot")

HELP = ("🤖 자동 대응 명령\n/ctl — 관리 페이지 로그인 링크\n/auto — 현황 요약\n/usage — 구독 사용량 조회\n/automode [auto|semi|off] — 동작 모드 보기/바꾸기\n"
        "/autopause — 분석 정지\n/autoresume — 분석 재개")


def _mask(tok: str) -> str:
    return tok[:4] + "…" + tok[-4:] if len(tok) > 10 else "***"


class BotCommands:
    """명령 처리(네트워크 없음 — 전송은 tg.send)."""

    def __init__(self, rx, cfg, tg, web_ctx: dict | None, chat_id: str, now=time.time):
        self.rx, self.cfg, self.tg, self.web, self.chat_id, self.now = rx, cfg, tg, web_ctx, str(chat_id), now

    def authorized(self, msg: dict) -> bool:
        chat = msg.get("chat") or {}
        return str(chat.get("id")) == self.chat_id and chat.get("type") == "private"

    def handle(self, update: dict) -> str | None:
        """처리한 명령 이름(없으면 None)."""
        msg = update.get("message") or {}
        text = (msg.get("text") or "").strip()
        if not text.startswith("/"):
            return None
        if not self.authorized(msg):
            log.warning("허용되지 않은 채팅의 명령 무시 (chat %s)", (msg.get("chat") or {}).get("id"))
            return None
        cmd = text.split()[0].split("@")[0].lower()
        self._args = text.split()[1:]
        fn = {"/ctl": self._ctl, "/auto": self._auto, "/autopause": self._pause, "/autoresume": self._resume,
              "/usage": self._usage, "/automode": self._mode, "/help": self._help, "/start": self._help}.get(cmd)
        if fn is None:
            self.tg.send("알 수 없는 명령입니다.\n\n" + HELP)
            return cmd
        try:
            fn()
        except Exception as e:  # noqa: BLE001
            log.exception("명령 처리 실패: %s", cmd)
            self.tg.send(f"⚠️ {cmd} 처리 실패: {type(e).__name__}: {str(e)[:120]}")
        return cmd

    def _mode(self):
        from .policy import MODES
        arg = (self._args[0].lower() if getattr(self, "_args", None) else "")
        if not arg:
            cur = self.rx.policy.mode()
            self.tg.send(f"현재 동작 모드: {MODES[cur]}({cur})\n바꾸려면 /automode auto | semi | off\n- auto 자동: 전부 자동 패치\n- semi 반자동: 패치 계획을 만들어 승인을 기다림\n- off 끔: 자동 대응 동작 안 함(기록만)")
            return
        r = self.rx.change_mode(arg, None, "telegram")
        if r.get("needs_queue"):
            self.tg.send(f"⚠️ 묶음 주기로 처리를 기다리는 에러가 {r['count']}건({r['types']}종류) 있습니다. 먼저 처리할지 버릴지 정해야 하므로 관리 페이지(/ctl)에서 모드를 바꿔 주세요.")
            return
        self.tg.send(f"✅ 동작 모드를 {MODES[r['mode']]}({r['mode']})(으)로 바꿨습니다." if r.get("ok") else f"⚠️ {(r.get('errors') or ['실패'])[0]}")

    def _help(self):
        self.tg.send(HELP)

    def _ctl(self):
        if not self.web:
            self.tg.send("관리 페이지가 꺼져 있습니다 (ADMIN_SECRET 없음 또는 RX_WEB=0).")
            return
        from .web import make_token
        tok = make_token(self.web["secret"], self.now())
        self.tg.send(f"🔐 자동 대응 관리 페이지 로그인 링크 (5분 · 1회용)\n{self.web['base']}/auth?t={tok}")

    def _auto(self):
        self.tg.send(status_text(build_status(self.rx, self.cfg, self.now())))

    def _pause(self):
        self.rx.set_pause(True)
        self.tg.send("⏸ 수신기 분석을 정지했습니다. 새 ERROR 이상 에러는 분석·수정 없이 기록만 합니다. (/autoresume 으로 재개)")

    def _resume(self):
        self.rx.set_pause(False)
        self.tg.send("▶ 수신기 분석을 재개했습니다.")

    def _usage(self):
        u, msg = self.rx.probe_usage()
        view = dict(u, age=int(self.now() - u.get("t", self.now()))) if u else None
        self.tg.send("\n".join(["📊 구독 사용량 (" + msg + ")", *usage_text(view)]))


class BotPoller:
    """getUpdates 장기 폴링 루프 (스레드)."""

    def __init__(self, token: str, handler: BotCommands, offset_path: Path, session=None, poll_timeout: int = 50):
        self.token, self.handler, self.offset_path = token, handler, offset_path
        self.session = session or requests.Session()
        self.poll_timeout = poll_timeout
        self.stop = threading.Event()
        self.base = f"https://api.telegram.org/bot{token}"
        self.state = "init"

    def webhook_ok(self) -> bool:
        try:
            info = self.session.get(f"{self.base}/getWebhookInfo", timeout=10).json()
            hook = ((info or {}).get("result") or {}).get("url") or ""
        except Exception as e:  # noqa: BLE001
            log.error("getWebhookInfo 실패(%s) — 안전을 위해 폴링을 시작하지 않음", type(e).__name__)
            return False
        if hook:
            log.error("이 봇(%s)에는 webhook 이 걸려 있다 — 운영 봇으로 보여 폴링 거부. 수신기 전용 새 봇 토큰을 쓰세요", _mask(self.token))
            return False
        return True

    def _offset(self) -> int:
        try:
            return int(self.offset_path.read_text().strip())
        except Exception:
            return 0

    def _save_offset(self, off: int) -> None:
        try:
            self.offset_path.write_text(str(off))
        except Exception:
            pass

    def poll_once(self) -> int:
        """한 번 가져와 처리. 처리한 업데이트 수. 오류는 예외로."""
        off = self._offset()
        r = self.session.get(f"{self.base}/getUpdates", params={"timeout": self.poll_timeout, "offset": off,
                                                                "allowed_updates": '["message"]'}, timeout=self.poll_timeout + 10)
        data = r.json()
        if not data.get("ok"):
            raise RuntimeError(f"getUpdates 실패: {str(data)[:120]}")
        n = 0
        for u in data.get("result", []):
            try:
                self.handler.handle(u)
            except Exception:
                log.exception("업데이트 처리 실패")
            off = max(off, u["update_id"] + 1)
            self._save_offset(off)
            n += 1
        return n

    def run(self) -> None:
        if not self.webhook_ok():
            self.state = "off"
            return
        log.info("수신기 전용 봇 폴링 시작 (%s)", _mask(self.token))
        self.state = "polling"
        backoff = 1.0
        while not self.stop.is_set():
            try:
                self.poll_once()
                backoff = 1.0
            except Exception as e:  # noqa: BLE001
                log.warning("봇 폴링 오류(%s) — %.0f초 후 재시도", type(e).__name__, backoff)
                self.stop.wait(backoff)
                backoff = min(backoff * 2, 60.0)


def start_bot(rx, cfg, tg, web_ctx, token: str, chat_id: str):
    handler = BotCommands(rx, cfg, tg, web_ctx, chat_id)
    poller = BotPoller(token, handler, cfg.rx / "tg_offset.txt")
    threading.Thread(target=poller.run, name="rx-bot", daemon=True).start()
    return poller
