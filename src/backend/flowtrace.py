"""(v4a) 흐름 기록 — 관리 페이지 작업 탭의 "최근 흐름"(경로 재생)용. **로컬 시험판 전용.**

알림 1건 · 관리 조작 1건 · 방송 확인 1건을 "흐름" 하나로 보고, 정해진 단계(예: 접수 → 원문 복원 → 분류 →
준비 → 적용 대기 → 반영)를 통과할 때마다 시각을 남긴다. 관리 페이지는 이걸 읽어 어디까지 갔는지,
어디서 멈췄는지를 순서도로 보여준다.

- 로컬(V4A_RUNTIME=local)이 아니면 전부 no-op. 배포판은 흐름마다 기록 커밋이 늘어 v3.9 식 브랜치 경합을
  부를 수 있어 따로 설계해야 한다(보류).
- 저장: `<LOCAL_DATA_DIR>/ops/flows.json` (최근 MAX_FLOWS 건). data 브랜치와 무관.
- 스레드 간 전달: 요청 스레드는 ContextVar(`current`), 적용 큐 작업은 작업 인자 `_flow` 로 흐름 id 를 넘긴다.
- 기록 실패는 본 처리에 영향을 주지 않는다(전부 예외 삼킴).

단계 상태: todo(아직) · run(처리 중) · wait(예약 시각까지 대기) · done · fail · skip(이 흐름엔 해당 없음).
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("backend.flowtrace")

MAX_FLOWS = 200

# 흐름 종류별 단계 (이름, 설명). 관리 페이지가 이 순서대로 그린다.
STAGES: dict[str, list[tuple[str, str]]] = {
    "x": [("접수", "X-Ingest-Secret 확인"), ("원문 복원", "vxtwitter"), ("분류", "개인 5인 · 공식"),
          ("준비", "Groq · videos.list"), ("적용 대기", "적용 큐"), ("반영", "data 쓰기")],
    "yt": [("접수", "X-Ingest-Secret 확인"), ("알림 해석", "YouTube 앱 알림"), ("준비", "영상 찾기 · 확인"),
           ("적용 대기", "적용 큐"), ("반영", "data 쓰기")],
    "admin": [("요청", "관리 페이지"), ("준비", "충돌 검사 · 파싱 · LLM"), ("적용 대기", "적용 큐"),
              ("반영", "data · ops 쓰기"), ("이력", "내가 한 조작")],
    "wake": [("예약", ""), ("대기", "예약 시각까지"), ("확인 · 반영", "videos.list → 상태 전이"),
             ("다음 확인", "")],
}

current: contextvars.ContextVar[str | None] = contextvars.ContextVar("flowtrace_current", default=None)

_lock = threading.RLock()
_flows: dict[str, dict] = {}      # id → 흐름 (삽입 순서 = 시작 순서)
_loaded = False


def enabled() -> bool:
    return os.environ.get("V4A_RUNTIME", "").strip().lower() == "local"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _path() -> Path:
    return Path(os.environ.get("LOCAL_DATA_DIR") or "./_local") / "ops" / "flows.json"


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        p = _path()
        if p.exists():
            for f in json.loads(p.read_text(encoding="utf-8")).get("flows", []):
                _flows[f["id"]] = f
    except Exception:  # noqa: BLE001
        log.warning("flows.json 읽기 실패 — 빈 상태로 시작", exc_info=True)


def _save() -> None:
    try:
        p = _path()
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps({"flows": list(_flows.values())}, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, p)
    except Exception:  # noqa: BLE001
        log.warning("flows.json 저장 실패", exc_info=True)


def fmt_dur(sec: float) -> str:
    """소요 시간 표기 — 0.23s · 12.3s · 12분 · 3시간 5분."""
    if sec < 10:
        return f"{sec:.2f}s"
    if sec < 60:
        return f"{sec:.1f}s"
    m = int(sec // 60)
    if m < 60:
        return f"{m}분"
    return f"{m // 60}시간" + (f" {m % 60}분" if m % 60 else "")


def start(cat: str, kind: str, desc: str = "", *, bind: bool = True, **extra) -> str | None:
    """흐름 시작 → id. bind=True 면 이 스레드(컨텍스트)의 current 로 둔다."""
    if not enabled() or cat not in STAGES:
        return None
    try:
        fid = uuid.uuid4().hex[:10]
        now = time.time()
        flow = {"id": fid, "cat": cat, "kind": kind, "desc": (desc or "")[:120], "t0": _now_iso(),
                "_t": now, "_last": now, "status": "run", "reason": "", "updated": _now_iso(),
                "stages": [{"n": n, "x": x, "s": "todo", "ms": "", "note": ""} for n, x in STAGES[cat]]}
        flow.update({k: v for k, v in extra.items() if v is not None})
        with _lock:
            _load()
            _flows[fid] = flow
            while len(_flows) > MAX_FLOWS:
                _flows.pop(next(iter(_flows)))
            _save()
        if bind:
            current.set(fid)
        return fid
    except Exception:  # noqa: BLE001
        log.warning("flowtrace.start 실패", exc_info=True)
        return None


@contextmanager
def bound(fid: str | None):
    """적용 큐 작업 안에서 그 작업의 흐름을 current 로."""
    token = current.set(fid)
    try:
        yield fid
    finally:
        current.reset(token)


def get(fid: str | None) -> dict | None:
    if not fid:
        return None
    with _lock:
        _load()
        f = _flows.get(fid)
        return json.loads(json.dumps(f)) if f else None


def mark(stage: str, s: str, note: str = "", *, fid: str | None = None, ms: str | None = None) -> None:
    """단계 상태 기록. 소요 시간(ms)은 직전 기록 이후 경과로 자동 계산(done · fail 일 때).

    이미 done 인 단계를 다시 done 으로 찍으면(같은 흐름이 작업을 두 번 적재) 소요 시간만 누적 표기하지 않고
    note 만 갱신한다. 흐름에 없는 단계 이름이면 무시.
    """
    fid = fid or current.get()
    if not fid or not enabled():
        return
    try:
        with _lock:
            _load()
            f = _flows.get(fid)
            if not f:
                return
            st = next((x for x in f["stages"] if x["n"] == stage), None)
            if st is None:
                return
            now = time.time()
            if s in ("done", "fail") and st["s"] != "done":
                st["ms"] = ms if ms is not None else fmt_dur(max(0.0, now - f["_last"]))
                f["_last"] = now
            elif ms is not None:
                st["ms"] = ms
            if s == "wait" and st["s"] == "todo":
                f["_last"] = now   # 대기 소요 시간은 대기에 들어간 순간부터 잰다
            st["s"] = s
            if note:
                st["note"] = note[:160]
            # 앞 단계 중 아직 todo 인 것은 이 흐름이 거치지 않은 단계 — skip
            idx = f["stages"].index(st)
            for prev in f["stages"][:idx]:
                if prev["s"] == "todo":
                    prev["s"] = "skip"
            if s == "fail":
                f["status"] = "fail"
            elif s == "wait" and f["status"] != "fail":
                f["status"] = "wait"
            elif s == "run" and f["status"] != "fail":
                f["status"] = "run"
            f["updated"] = _now_iso()
            _save()
    except Exception:  # noqa: BLE001
        log.warning("flowtrace.mark 실패", exc_info=True)


def stage_state(stage: str, fid: str | None = None) -> str | None:
    f = get(fid or current.get())
    if not f:
        return None
    st = next((x for x in f["stages"] if x["n"] == stage), None)
    return st["s"] if st else None


def finish(reason: str = "", *, fid: str | None = None, fail: bool = False) -> None:
    """흐름 종료. 남은 todo · run 단계는 skip(거치지 않음)으로, 상태는 fail 이 하나라도 있으면 fail."""
    fid = fid or current.get()
    if not fid or not enabled():
        return
    try:
        with _lock:
            _load()
            f = _flows.get(fid)
            if not f:
                return
            for st in f["stages"]:
                if st["s"] in ("todo", "run"):
                    st["s"] = "skip"
            bad = fail or any(st["s"] == "fail" for st in f["stages"])
            f["status"] = "fail" if bad else "ok"
            f["total"] = fmt_dur(max(0.0, time.time() - f["_t"]))
            if reason:
                f["reason"] = reason[:400]
            f["updated"] = _now_iso()
            _save()
    except Exception:  # noqa: BLE001
        log.warning("flowtrace.finish 실패", exc_info=True)


def set_reason(reason: str, *, fid: str | None = None) -> None:
    fid = fid or current.get()
    if not fid or not enabled():
        return
    with _lock:
        _load()
        f = _flows.get(fid)
        if f:
            f["reason"] = reason[:400]
            f["updated"] = _now_iso()
            _save()


def annotate(*, fid: str | None = None, **kv) -> None:
    """흐름에 필드를 붙인다(예: detached=True — 결과를 안 기다린 작업이라 적용 큐 워커가 마무리)."""
    fid = fid or current.get()
    if not fid or not enabled():
        return
    with _lock:
        _load()
        f = _flows.get(fid)
        if f:
            f.update(kv)
            _save()


def add_llm(info: dict, *, fid: str | None = None) -> None:
    """(v4a) 흐름에 LLM 판단 1건을 붙인다 — 작업 탭 「LLM 판단」 필터 · 되돌리기. info = {"id","kind","summary","undo"}."""
    fid = fid or current.get()
    if not fid or not enabled():
        return
    with _lock:
        _load()
        f = _flows.get(fid)
        if f:
            f.setdefault("llm", []).append(info)
            _save()


def is_open(fid: str | None = None) -> bool:
    f = get(fid or current.get())
    return bool(f) and f["status"] in ("run", "wait")


def list_flows(limit: int = MAX_FLOWS) -> list[dict]:
    """최근 흐름(최신 먼저). 내부 필드(_t · _last)는 뺀다."""
    with _lock:
        _load()
        out = [{k: v for k, v in f.items() if not k.startswith("_")} for f in _flows.values()]
    return list(reversed(out))[:limit]


if __name__ == "__main__":
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        os.environ.update({"V4A_RUNTIME": "local", "LOCAL_DATA_DIR": d})
        # X 알림: 접수 → (원문 복원 없음) → 분류 → 준비 → 적용 대기 → 반영
        fid = start("x", "X 알림", "테스트")
        mark("접수", "done")
        mark("분류", "done", "공식 → 스케줄")
        f = get(fid)
        assert [s["s"] for s in f["stages"]][:3] == ["done", "skip", "done"], f["stages"]
        mark("준비", "done")
        mark("적용 대기", "run")
        assert get(fid)["status"] == "run"
        mark("적용 대기", "done")
        mark("반영", "done", "merge_rows")
        finish("완료")
        f = get(fid)
        assert f["status"] == "ok" and f["reason"] == "완료" and f["total"], f
        # 인증 실패: 접수 fail → 나머지 skip, 상태 fail
        fid2 = start("x", "X 알림", "403")
        mark("접수", "fail", "인증 실패")
        finish("인증 실패")
        f2 = get(fid2)
        assert f2["status"] == "fail" and all(s["s"] == "skip" for s in f2["stages"][1:]), f2
        # 방송 확인: 예약 → 대기(wait) → 다른 스레드에서 이어받기
        fid3 = start("wake", "방송 확인", "vid", bind=False)
        mark("예약", "done", fid=fid3)
        mark("대기", "wait", "22:10", fid=fid3)
        assert get(fid3)["status"] == "wait"
        with bound(fid3):
            mark("대기", "done")
            mark("확인 · 반영", "done", "변화 없음")
            finish("완료")
        f3 = get(fid3)
        assert f3["status"] == "ok" and f3["stages"][3]["s"] == "skip", f3
        # 파일 저장 · 목록 순서(최신 먼저) · 내부 필드 제거
        assert (Path(d) / "ops" / "flows.json").exists()
        lst = list_flows()
        assert [x["id"] for x in lst] == [fid3, fid2, fid] and "_t" not in lst[0]
        # 비로컬이면 no-op
        os.environ["V4A_RUNTIME"] = ""
        assert start("x", "X 알림") is None
        assert fmt_dur(0.234) == "0.23s" and fmt_dur(75) == "1분" and fmt_dur(3900) == "1시간 5분"
    print("[PASS] flowtrace self-test: 단계 기록 · skip 채움 · 실패 · 대기/이어받기 · 저장 · 비로컬 no-op")
