"""발신기 — 로그 · 이벤트를 봉투(mew.err/1)로 버스에 내보내고, 제어 봉투(mew.ctl/1)를 받아 반영한다.

규약: docs/BUS_PROTOCOL.md. 원칙: **발신기는 서비스를 절대 방해하지 않는다** — 모든 경로가 예외를 삼키고
카운터로만 남긴다. MEW_BUS_DIR 이 없으면 install() 은 None 을 돌려주고 아무 것도 붙이지 않는다.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
import traceback as _tb
from collections import deque
from pathlib import Path

from . import envelope as E
from .redact import redact
from .spool import INBOX_CAP, Spool

COALESCE_WINDOW_SEC = 60      # 같은 시그니처는 첫 건만 즉시 보내고 이 창 안의 반복은 묶어 요약 1건
RATE_MAX_PER_MIN = 60         # 분당 발신 상한(CRITICAL 제외)
CTL_POLL_SEC = 5
HB_SEC = 30
VERBOSE_DEFAULT_TTL = 3600    # set_level INFO/DEBUG 에 ttl 이 없을 때(상세 레벨은 항상 자동 복귀)

_LEVELS = ("ERROR", "WARN", "INFO", "DEBUG")
_VERBOSE = ("INFO", "DEBUG")
_UC = re.compile(r"UC[\w-]{22}")
_HEX = re.compile(r"\b[0-9a-fA-F]{8,}\b")
_NUM = re.compile(r"\d+")
_WS = re.compile(r"\s+")
_log = logging.getLogger("src.bus")


def _normalize(msg: str) -> str:
    s = _UC.sub("UC*", msg)
    s = _HEX.sub("H", s)
    s = _NUM.sub("N", s)
    return _WS.sub(" ", s).strip()[:160]


def _level_to_sev(levelno: int) -> str | None:
    if levelno >= logging.CRITICAL:
        return "CRITICAL"
    if levelno >= logging.ERROR:
        return "ERROR"
    if levelno >= logging.WARNING:
        return "WARN"
    if levelno >= logging.INFO:
        return "INFO"
    if levelno >= logging.DEBUG:
        return "DEBUG"
    return "DEBUG"  # DEBUG(10) 미만도 DEBUG (TRACE 는 폐기)


class Publisher:
    def __init__(self, root, *, env: str = "local", service: str = "runner", level: str = "WARN",
                 clock=time.time, start_thread: bool = True):
        self.spool = Spool(root)
        self.spool.ensure()
        self.env, self.service = env, service
        self.source = E.make_source(env, service)
        self.base_level = self.level = level if level in _LEVELS else "WARN"
        self._level_until: float | None = None
        self.paused = False
        self._paused_until: float | None = None
        self.clock = clock
        self.counters = {"sent": 0, "coalesced": 0, "dropped": 0, "suppressed": 0, "errors": 0}
        self._win: dict[tuple, dict] = {}
        self._sent_times: deque[float] = deque()
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_ctl = self._last_hb = 0.0
        self._saved_root: tuple | None = None
        if start_thread:
            self._thread = threading.Thread(target=self._loop, name="bus-publisher", daemon=True)
            self._thread.start()

    # ── 발신 ─────────────────────────────────────────────
    def emit(self, *, kind: str, severity: str, message: str, logger: str = "", traceback: str = "",
             event: dict | None = None, context: dict | None = None) -> None:
        try:
            self._emit(kind, severity, message, logger, traceback, event, context)
        except Exception:
            self.counters["errors"] += 1  # 서비스 방해 금지 — 삼킨다

    def _emit(self, kind, severity, message, logger, traceback, event, context) -> None:
        now = self.clock()
        with self._lock:
            self._tick_state(now)
            crit = severity == "CRITICAL"
            if self.paused and not crit:
                self.counters["suppressed"] += 1
                return
            if E.rank(severity) < E.rank(self.level):
                return
            message = redact(message)
            traceback = redact(traceback)
            if event and event.get("detail"):
                event = {**event, "detail": redact(str(event["detail"]))}
            if context:
                context = {k: redact(v) if isinstance(v, str) else v for k, v in context.items()}
            ts = E.iso(now)
            if not crit:
                key = (severity, logger or (event or {}).get("flow", ""), _normalize(message))
                w = self._win.get(key)
                if w and now - w["first"] < COALESCE_WINDOW_SEC:
                    w["count"] += 1
                    w["last"] = ts
                    self.counters["coalesced"] += 1
                    return
                if w:
                    self._flush_one(key, w)
                self._win[key] = {"first": now, "first_ts": ts, "last": ts, "count": 1, "args": dict(
                    kind=kind, severity=severity, message=message, logger=logger, event=event, context=context)}
            self._send(E.build_err(kind=kind, severity=severity, message=message, source=self.source,
                                   logger=logger, traceback=traceback, event=event, context=context, ts=ts), crit)

    def _send(self, env: dict, crit: bool) -> None:
        now = self.clock()
        if not crit:
            while self._sent_times and now - self._sent_times[0] > 60:
                self._sent_times.popleft()
            if len(self._sent_times) >= RATE_MAX_PER_MIN or self.spool.count("err/inbox") >= INBOX_CAP:
                self.counters["dropped"] += 1
                return
            self._sent_times.append(now)
        name = f"{env['ts'].replace('-', '').replace(':', '')}_{env['id']}"
        self.spool.put("err/inbox", name, env)
        self.counters["sent"] += 1

    def _flush_one(self, key, w) -> None:
        extra = w["count"] - 1  # 첫 건은 이미 개별 발신됨 — 요약은 그 뒤 반복분
        if extra >= 1:
            a = w["args"]
            self._send(E.build_err(kind=a["kind"], severity=a["severity"], message=a["message"],
                                   source=self.source, logger=a["logger"], event=a["event"], context=a["context"],
                                   occurrences=extra, first_ts=w["first_ts"], last_ts=w["last"],
                                   ts=E.iso(self.clock())), False)
        self._win.pop(key, None)

    def flush_expired(self) -> None:
        now = self.clock()
        with self._lock:
            for key, w in list(self._win.items()):
                if now - w["first"] >= COALESCE_WINDOW_SEC:
                    self._flush_one(key, w)

    # ── 이벤트 로그 훅 (monitor_log.log_events 에서 호출) ─────
    def on_events(self, events: list[dict]) -> None:
        for ev in events:
            result = ev.get("result")
            if result == "degraded":      # 옛 기록 값 — warn 으로 통일
                result = "warn"
            # err = ERROR · warn(구 degraded) = WARN · ok = INFO (docs/BUS_PROTOCOL.md §1-1)
            sev = "ERROR" if result == "err" else ("WARN" if result in ("warn", "degraded") else "INFO")
            flow = str(ev.get("flow", ""))
            detail = str(ev.get("detail", ""))
            ctx = {k: v for k, v in ev.items()
                   if k not in ("ts", "flow", "result", "who", "detail") and isinstance(v, (str, int, float, bool))}
            ctx = {k: (v[:200] if isinstance(v, str) else v) for k, v in list(ctx.items())[:20]}
            first = detail.splitlines()[0] if detail else ""
            self.emit(kind="event", severity=sev, message=f"[{flow}] {result}: {first}", logger="",
                      event={"flow": flow, "result": result, "who": ev.get("who", ""), "detail": detail},
                      context=ctx or None)

    # ── 상태 · 제어 ───────────────────────────────────────
    def _tick_state(self, now: float) -> None:
        if self._level_until is not None and now >= self._level_until:
            self.level, self._level_until = self.base_level, None
            self._sync_logging()
        if self._paused_until is not None and now >= self._paused_until:
            self.paused, self._paused_until = False, None

    def _sync_logging(self) -> None:
        """DEBUG 발신 중에는 루트 로거 레벨을 낮춰 debug 로그가 핸들러까지 오게 하고,
        기존 핸들러(콘솔 등)는 원래 루트 레벨로 묶어 출력은 그대로 둔다. 레벨이 내려오면 원복."""
        root = logging.getLogger()
        want = logging.DEBUG if self.level == "DEBUG" else None
        if want is not None:
            if self._saved_root is None:
                orig = root.level or logging.WARNING
                others = [(h, h.level) for h in root.handlers if not isinstance(h, BusLogHandler)]
                self._saved_root = (root.level, others)
                for h, lv in others:
                    h.setLevel(max(lv, orig))
            root.setLevel(want)
        elif self._saved_root is not None:
            lvl, others = self._saved_root
            root.setLevel(lvl)
            for h, lv in others:
                h.setLevel(lv)
            self._saved_root = None

    def poll_ctl(self) -> None:
        for p in self.spool.list("ctl/inbox"):
            try:
                obj = json.loads(p.read_text(encoding="utf-8"))
            except Exception as e:
                self._ctl_done(p, None, False, f"읽기 실패: {e}")
                continue
            tgt = obj.get("target")
            if tgt not in (None, "", "publisher", "*"):
                continue  # 다른 대상 몫 — 건드리지 않음
            from .conform import validate
            errs = validate(obj) if obj.get("schema") == "mew.ctl/1" else ["schema 가 mew.ctl/1 아님"]
            if errs:
                self._ctl_done(p, obj, False, "; ".join(errs))
                continue
            ok, detail = self._apply_ctl(obj)
            self._ctl_done(p, obj, ok, detail)

    def _apply_ctl(self, c: dict) -> tuple[bool, str]:
        cmd, args, now = c["cmd"], c.get("args") or {}, self.clock()
        with self._lock:
            if cmd == "set_level":
                lvl = args.get("level")
                if lvl not in _LEVELS:
                    return False, "level 은 ERROR/WARN/INFO/DEBUG"
                ttl = args.get("ttl_sec") or (VERBOSE_DEFAULT_TTL if lvl in _VERBOSE else None)
                if ttl:
                    self.level, self._level_until = lvl, now + min(int(ttl), 86400)
                    self._sync_logging()
                    return True, f"level={lvl} {int(ttl)}초 뒤 {self.base_level} 로 복귀"
                self.base_level = self.level = lvl
                self._level_until = None
                self._sync_logging()
                return True, f"level={lvl} (유지)"
            if cmd == "pause":
                ttl = args.get("ttl_sec")
                self.paused, self._paused_until = True, (now + int(ttl) if ttl else None)
                return True, "pause (CRITICAL 은 계속 발신)" + (f", {int(ttl)}초 뒤 자동 재개" if ttl else "")
            if cmd == "resume":
                self.paused, self._paused_until = False, None
                return True, "resume"
            if cmd == "ping":
                self.write_hb()
                return True, "pong"
        return False, f"알 수 없는 cmd {cmd}"

    def _ctl_done(self, path: Path, obj, ok: bool, detail: str) -> None:
        try:
            self.spool.put("ctl/done", path.stem, {"ctl": obj, "applied": ok, "detail": detail,
                                                   "applied_at": E.iso(self.clock())})
            path.unlink(missing_ok=True)
        except Exception:
            self.counters["errors"] += 1

    def write_hb(self) -> None:
        try:
            self.spool.put("hb", "publisher", {
                "schema": "mew.hb/1", "role": "publisher", "ts": E.iso(self.clock()), "pid": os.getpid(),
                "env": self.env, "level": self.level, "paused": self.paused, "counters": dict(self.counters)})
        except Exception:
            self.counters["errors"] += 1

    def _loop(self) -> None:
        while not self._stop.wait(2.0):
            try:
                now = self.clock()
                self.flush_expired()
                with self._lock:
                    self._tick_state(now)
                if now - self._last_ctl >= CTL_POLL_SEC:
                    self._last_ctl = now
                    self.poll_ctl()
                if now - self._last_hb >= HB_SEC:
                    self._last_hb = now
                    self.write_hb()
            except Exception:
                self.counters["errors"] += 1

    def stop(self) -> None:
        self._stop.set()


class BusLogHandler(logging.Handler):
    def __init__(self, pub: Publisher):
        super().__init__(level=logging.NOTSET)
        self.pub = pub

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name.startswith("src.bus"):
                return
            sev = _level_to_sev(record.levelno)
            if not sev:
                return
            tb = "".join(_tb.format_exception(*record.exc_info)) if record.exc_info else ""
            self.pub.emit(kind="log", severity=sev, message=record.getMessage(), logger=record.name,
                          traceback=tb, context={"thread": record.threadName} if record.threadName else None)
        except Exception:
            pass


# ── 모듈 수준 진입점 ──────────────────────────────────────
_pub: Publisher | None = None


def get() -> Publisher | None:
    return _pub


def on_events(events: list[dict]) -> None:
    """monitor_log.log_events 가 부르는 훅 — 설치 안 됐으면 no-op, 절대 예외를 던지지 않는다."""
    p = _pub
    if p is not None:
        try:
            p.on_events(events)
        except Exception:
            pass


def install(*, env: str | None = None, service: str = "runner") -> Publisher | None:
    """루트 로거 핸들러 + 미처리 예외 훅(CRITICAL)을 붙인다. MEW_BUS_DIR 없으면 None."""
    global _pub
    if _pub is not None:
        return _pub
    root = os.environ.get("MEW_BUS_DIR", "").strip()
    if not root:
        return None
    try:
        pub = Publisher(root, env=env or os.environ.get("MEW_ENV", "local"), service=service,
                        level=os.environ.get("MEW_BUS_LEVEL", "WARN").upper())
    except Exception as e:  # 버스 폴더를 못 만들어도 서비스는 계속
        logging.getLogger("src.bus").warning("버스 발신기 비활성: %s", e)
        return None
    logging.getLogger().addHandler(BusLogHandler(pub))

    prev_exc = sys.excepthook

    def _exc(tp, val, tb):
        pub.emit(kind="log", severity="CRITICAL", message=f"처리되지 않은 예외로 프로세스 종료: {tp.__name__}: {val}",
                 logger="uncaught.process", traceback="".join(_tb.format_exception(tp, val, tb)))
        prev_exc(tp, val, tb)

    sys.excepthook = _exc
    prev_thr = threading.excepthook

    def _thr(args):
        name = args.thread.name if args.thread else "?"
        pub.emit(kind="log", severity="CRITICAL", message=f"처리되지 않은 예외로 스레드 {name} 종료: "
                 f"{args.exc_type.__name__}: {args.exc_value}", logger="uncaught.thread",
                 traceback="".join(_tb.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
        prev_thr(args)

    threading.excepthook = _thr
    _pub = pub
    pub.write_hb()
    logging.getLogger("src.bus").info("버스 발신기 시작: %s (level=%s)", root, pub.level)
    return pub


if __name__ == "__main__":
    import tempfile

    from .conform import validate

    def check(cond, msg):
        assert cond, msg
        print("OK ", msg)

    tmp = tempfile.mkdtemp(prefix="mewbus_")
    now = [1_800_000_000.0]
    pub = Publisher(tmp, clock=lambda: now[0], start_thread=False)
    sp = pub.spool

    def inbox():
        return [json.loads(p.read_text(encoding="utf-8")) for p in sp.list("err/inbox")]

    # 1) 마스킹
    os.environ["FAKE_API_KEY"] = "abcd1234efgh5678"
    pub.emit(kind="log", severity="ERROR", message="403 url=https://x/v?key=SECRET99&part=a token abcd1234efgh5678",
             logger="t.a")
    m = inbox()[0]
    check("SECRET99" not in m["message"] and "abcd1234efgh5678" not in m["message"], "비밀값 마스킹")
    check(not validate(m), "ERROR 봉투가 스키마에 적합")

    # 2) WARN 기본 발신 · INFO 기본 미발신
    n0 = len(inbox())
    pub.emit(kind="log", severity="INFO", message="정보", logger="t.b")
    check(len(inbox()) == n0, "INFO 는 기본 미발신")
    pub.emit(kind="log", severity="WARN", message="경고 하나", logger="t.c")
    check(len(inbox()) == n0 + 1, "WARN 은 발신")

    # 3) 묶음: 같은 시그니처 반복 → 첫 건 즉시 + 창 종료 후 요약(반복분 수)
    base = len(inbox())
    for i in range(5):
        pub.emit(kind="log", severity="WARN", message=f"Failed to fetch RSS for channel UC{'a'*22}: 404 try {i}", logger="rss")
    check(len(inbox()) == base + 1, "반복 5건 중 첫 건만 즉시 발신")
    now[0] += COALESCE_WINDOW_SEC + 1
    pub.flush_expired()
    s = inbox()[-1]
    check(s.get("occurrences") == 4 and not validate(s), "요약 봉투 occurrences=반복분(4) + 적합")

    # 4) ctl: set_level INFO ttl → 발신 → 만료 후 복귀
    sp.put("ctl/inbox", "c1", {"schema": "mew.ctl/1", "id": E.new_id(), "ts": E.iso(now[0]), "cmd": "set_level",
                               "args": {"level": "INFO", "ttl_sec": 100}})
    pub.poll_ctl()
    check(pub.level == "INFO", "set_level INFO 적용")
    check(sp.count("ctl/inbox") == 0 and sp.count("ctl/done") == 1, "ctl 처리 결과가 ctl/done 에 남음")
    n1 = len(inbox())
    pub.emit(kind="log", severity="INFO", message="자세히", logger="t.d")
    check(len(inbox()) == n1 + 1, "INFO 레벨에서 INFO 발신")
    now[0] += 101
    pub.emit(kind="log", severity="INFO", message="자세히2", logger="t.e")
    check(pub.level == "WARN" and len(inbox()) == n1 + 1, "ttl 만료 후 WARN 으로 복귀")

    # 4-b) DEBUG: 단계 순서 · 루트 로거 레벨 조정 · 원복
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    sp.put("ctl/inbox", "c1b", {"schema": "mew.ctl/1", "id": E.new_id(), "ts": E.iso(now[0]), "cmd": "set_level",
                                "args": {"level": "DEBUG", "ttl_sec": 100}})
    pub.poll_ctl()
    check(pub.level == "DEBUG" and root.level == logging.DEBUG, "set_level DEBUG → 루트 로거 DEBUG 로 낮춤")
    n1b = len(inbox())
    pub.emit(kind="log", severity="DEBUG", message="디버그 로그", logger="t.dbg")
    got_b = inbox()[n1b:]
    check(len(got_b) == 1 and got_b[0]["severity"] == "DEBUG" and not validate(got_b[0]), "DEBUG 레벨에서 DEBUG 발신")
    sp.put("ctl/inbox", "c1c", {"schema": "mew.ctl/1", "id": E.new_id(), "ts": E.iso(now[0]), "cmd": "set_level",
                                "args": {"level": "TRACE", "ttl_sec": 100}})
    pub.poll_ctl()
    check(pub.level == "DEBUG" and sp.count("ctl/inbox") == 0, "폐기된 TRACE 레벨 요청은 거부되고 현재 레벨 유지")
    check(_level_to_sev(logging.DEBUG) == "DEBUG" and _level_to_sev(5) == "DEBUG" and _level_to_sev(logging.WARNING) == "WARN",
          "logging 레벨 → 심각도 변환(DEBUG 미만도 DEBUG · WARN)")
    now[0] += 101
    pub.emit(kind="log", severity="INFO", message="만료 확인", logger="t.exp")
    check(pub.level == "WARN" and root.level == logging.INFO, "ttl 만료 후 루트 로거 레벨 원복")

    # 5) pause: ERROR 억제 · CRITICAL 통과
    sp.put("ctl/inbox", "c2", {"schema": "mew.ctl/1", "id": E.new_id(), "ts": E.iso(now[0]), "cmd": "pause"})
    pub.poll_ctl()
    n2 = len(inbox())
    pub.emit(kind="log", severity="ERROR", message="멈춘 중 에러", logger="t.f")
    pub.emit(kind="log", severity="CRITICAL", message="치명", logger="t.g")
    check(len(inbox()) == n2 + 1 and inbox()[-1]["severity"] == "CRITICAL", "pause 중 ERROR 억제 · CRITICAL 통과")
    sp.put("ctl/inbox", "c3", {"schema": "mew.ctl/1", "id": E.new_id(), "ts": E.iso(now[0]), "cmd": "resume"})
    pub.poll_ctl()
    check(not pub.paused, "resume")

    # 6) 잘못된 ctl · 다른 대상
    sp.put("ctl/inbox", "c4", {"schema": "mew.ctl/1", "id": E.new_id(), "ts": E.iso(now[0]), "cmd": "set_level",
                               "args": {"level": "CRITICAL"}})
    sp.put("ctl/inbox", "c5", {"schema": "mew.ctl/1", "id": E.new_id(), "ts": E.iso(now[0]), "cmd": "pause",
                               "target": "other"})
    pub.poll_ctl()
    check(not pub.paused and sp.count("ctl/inbox") == 1, "잘못된 ctl 은 거부 · 다른 대상은 그대로 둠")

    # 7) 이벤트 훅
    n3 = len(inbox())
    pub.on_events([{"flow": "song", "result": "warn", "who": "group", "detail": "RSS 비어 있음", "ts": "x"},
                   {"flow": "tick", "result": "ok", "detail": "정상"},
                   {"flow": "tweet", "result": "err", "detail": "반영 실패"}])
    got = inbox()[n3:]
    check(len(got) == 2 and [g["severity"] for g in got] == ["WARN", "ERROR"] and all(g["kind"] == "event" and not validate(g) for g in got),
          "이벤트 warn→WARN · err→ERROR 발신, ok→INFO(기본 미발신)")
    n3b = len(inbox())
    pub.on_events([{"flow": "song", "result": "degraded", "detail": "옛 기록 값"}])
    check(len(inbox()) == n3b + 1 and inbox()[-1]["severity"] == "WARN", "옛 result 값 degraded 는 warn 으로 취급(WARN)")

    # 8) 로깅 핸들러 · traceback
    lg = logging.getLogger("selftest.handler")
    h = BusLogHandler(pub)
    lg.addHandler(h)
    lg.propagate = False
    lg.setLevel(logging.INFO)
    n4 = len(inbox())
    try:
        raise ValueError("boom")
    except ValueError:
        lg.exception("실패 처리")
    last = inbox()[n4]
    check(last["severity"] == "ERROR" and "ValueError: boom" in last["traceback"] and not validate(last),
          "logging.exception → traceback 포함 ERROR 봉투")

    # 9) 발신 상한 · inbox 상한 · 원자성
    for i in range(RATE_MAX_PER_MIN + 20):
        pub.emit(kind="log", severity="ERROR", message=f"고유 메시지 {'x' * i}", logger=f"flood{i}")
    check(pub.counters["dropped"] > 0, "분당 상한 초과분은 dropped 로 집계")
    check(not list((Path(tmp) / "err" / "inbox").glob("*.tmp")) and not list((Path(tmp) / ".tmp").glob("*")),
          "tmp 잔여물 없음(원자적 기록)")
    pub.write_hb()
    check(not validate(json.loads((Path(tmp) / "hb" / "publisher.json").read_text(encoding="utf-8"))), "hb 적합")
    print("모두 통과")
