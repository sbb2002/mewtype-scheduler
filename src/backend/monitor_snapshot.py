"""(v3.8.9) 모니터링 스냅샷(용어: docs/TERMINOLOGY.md) — 일별 스냅샷 + 전 기간 요약. 웹 monitor(이스터에그)를 전 기간
리포트로 쓰기 위한 저장 계층.

배경: 지나간 날짜의 이벤트 로그(`monitoring/events-YYYY-MM-DD.jsonl`)는 06:00 KST 경계가
지나면 더 이상 늘지 않는다(monitor_log 는 기록 시각 기준 버킷에만 append). 그러니 매번
수백 개 파일을 다시 읽을 필요 없이, 하루가 끝나면 한 번만 계산해 굳혀 두고 웹 monitor 는
"오늘"만 실시간으로 계산한다.

저장 (data 저장소):
  monitoring/days/YYYY-MM-DD.json  — 그날 하루치 상세(monitor_report.build_day_from_text
                                     결과 + date/snapshotAt). 잔디 칸을 누를 때만 읽는다.
  monitoring/summary.json          — {"days": {"YYYY-MM-DD": 요약}, "backfill_complete": bool}.
                                     요약 = {"triggers": N, "events": M} 또는
                                     {"no_log": true}(그날 이벤트 로그 파일이 없음 —
                                     0건인지 기록 누락인지 구분 불가라 숫자를 안 넣음).

추측 금지 원칙: 외부 조회(healthchecks.io 다운 구간, Vercel 배포 시도 수)가 실패하면 None
("확인 불가")으로 저장한다 — 빈 목록/0 으로 채우면 "정상"으로 단정하는 것이 된다.
스냅샷은 사후 조회 결과이므로 `snapshotAt`(조회 시각)을 같이 남긴다.

호출: app.py `_monitor()`(Cloud Scheduler, 매일 KST 06:10) → `run_daily()`.
  - 전날(방금 끝난 하루)은 항상 스냅샷(이미 있으면 = 스케줄러 재시도 → 건너뜀).
  - 백필 미완료(summary.json `backfill_complete` false)면 `monitoring/` 의 이벤트 로그 파일
    목록으로 과거 날짜를 찾아 채운다(로그 파일이 있는 날짜만 — 로그 시작 이전 날짜를
    만들어내지 않는다).
  - 백필 완료 뒤엔 "마지막 요약 날짜 다음 날 ~ 전날" 공백(스케줄러 누락분)을 채운다.
  - 한 번에 MAX_PER_RUN 일까지만(스케줄러 요청 시간 제한) — 남은 날은 다음 실행이 이어서.

self-test: python -m src.backend.monitor_snapshot
"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timedelta

from . import monitor_report
from .monitor_log import DAY_START_HOUR

logger = logging.getLogger(__name__)

SUMMARY_PATH = "monitoring/summary.json"
MAX_PER_RUN = 10
_EVENTS_RE = re.compile(r"^events-(\d{4}-\d{2}-\d{2})\.jsonl$")


def day_path(date_kst: str) -> str:
    return f"monitoring/days/{date_kst}.json"


def summary_entry(day: dict) -> dict:
    """하루치 dict → 잔디용 요약. 로그 파일이 없던 날은 숫자 대신 no_log."""
    if not day.get("hasLog"):
        return {"no_log": True}
    if day.get("backfillOnly"):  # 사후 복원 기록뿐 — 트리거 수를 단정하지 않는다
        return {"backfill_only": True, "events": day["eventCount"]}
    return {"triggers": monitor_report.day_trigger_count(day), "events": day["eventCount"]}


def _dates_between(first: str, last: str) -> list[str]:
    """first~last(포함) 날짜 목록. first > last 면 []."""
    d = datetime.strptime(first, "%Y-%m-%d")
    end = datetime.strptime(last, "%Y-%m-%d")
    out = []
    while d <= end:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def pending_dates(summary_days: dict, yesterday: str, event_dates: list[str] | None,
                  backfill_complete: bool) -> tuple[list[str], bool]:
    """이번 실행에서 스냅샷할 날짜(오름차순, 최대 MAX_PER_RUN)와 실행 후 백필 완료 여부.

    - 백필 미완료(event_dates 필요): 로그 파일이 있는 날짜 중 전날 이전이면서 요약에 없는
      것을 오래된 순으로. 상한에 걸려 남으면 완료=False 로 두고 다음 실행이 이어서 한다
      (로그 시작 이전 날짜는 만들어내지 않는다).
    - 백필 완료: 마지막 요약 날짜 다음 날 ~ 전날 전 누락분(스케줄러가 빠진 날). 로그 파일이
      없던 날이면 스냅샷이 no_log 로 기록한다 — 로그 시작 이후 날짜이므로 "파일 없음" 자체가 사실.
    - 전날은 요약에 없으면 항상 포함(이미 있으면 = 스케줄러 재시도 → 건너뜀).
    순수 함수.
    """
    budget = MAX_PER_RUN - (0 if yesterday in summary_days else 1)
    if not backfill_complete:
        todo = sorted(d for d in (event_dates or []) if d < yesterday and d not in summary_days)
    elif summary_days:
        # 가장 최근 요약 날짜 "이후"만 — 최초 백필이 로그 파일이 없어 일부러 건너뛴 사이
        # 날짜를 나중에 다시 끼워 넣지 않는다.
        nxt = (datetime.strptime(max(summary_days), "%Y-%m-%d") + timedelta(days=1)).strftime("%Y-%m-%d")
        todo = [d for d in _dates_between(nxt, yesterday) if d != yesterday]
    else:
        todo = []
    out = todo[:budget]
    complete = len(todo) <= budget
    if yesterday not in summary_days:
        out.append(yesterday)
    return out, complete


def snapshot_day(gh, date_kst: str, *, healthchecks_api_key: str, healthchecks_uuid: str,
                 vercel_token: str, now_iso: str) -> dict:
    """그날 하루치를 계산해 `monitoring/days/{date}.json` 에 쓰고 dict 를 돌려준다."""
    text, _sha = gh.read_text(f"monitoring/events-{date_kst}.jsonl")
    day = monitor_report.build_day_from_text(
        date_kst, text, now_hm=None,
        down_ranges=monitor_report._fetch_health_down_ranges(
            healthchecks_api_key, healthchecks_uuid, date_kst),
        vercel_deploys=monitor_report._vercel_deploys(vercel_token, date_kst),
    )
    day["date"] = date_kst
    day["snapshotAt"] = now_iso
    _write_json_retry(gh, day_path(date_kst), day, f"data: monitor snapshot {date_kst}")
    return day


def _write_json_retry(gh, path: str, data: dict, message: str) -> None:
    """write_json(prev_sha=None 이면 매번 현재 sha 로 씀) — 같은 브랜치에 다른 커밋이 동시에
    들어와 409 가 나면 한 번 더 시도."""
    from .gh_store import ConflictError

    for attempt in range(2):
        try:
            gh.write_json(path, data, prev_sha=None, message=message)
            return
        except ConflictError:
            if attempt == 1:
                raise
            logger.warning("monitor_snapshot: %s 충돌 — 재시도", path)


def read_summary(gh) -> tuple[dict, bool]:
    """summary.json → (days dict, backfill_complete). 없으면 ({}, False)."""
    data, _sha = gh.read_json(SUMMARY_PATH)
    data = data or {}
    return dict(data.get("days") or {}), bool(data.get("backfill_complete"))


def read_day(gh, date_kst: str) -> dict | None:
    data, _sha = gh.read_json(day_path(date_kst))
    return data


def run_daily(gh, *, today_bucket: str, now_iso: str, healthchecks_api_key: str,
              healthchecks_uuid: str, vercel_token: str) -> dict:
    """스케줄러 진입점. {"yesterday": 전날 dict, "snapshotted": [날짜...], "summary": days}."""
    yesterday = (datetime.strptime(today_bucket, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    summary_days, backfill_complete = read_summary(gh)
    event_dates = None
    if not backfill_complete:
        event_dates = [m.group(1) for n in gh.list_dir("monitoring") if (m := _EVENTS_RE.match(n))]
    targets, complete_after = pending_dates(summary_days, yesterday, event_dates, backfill_complete)

    kw = dict(healthchecks_api_key=healthchecks_api_key, healthchecks_uuid=healthchecks_uuid,
              vercel_token=vercel_token, now_iso=now_iso)
    yesterday_day = None
    done = []
    for d in targets:
        try:
            day = snapshot_day(gh, d, **kw)
        except Exception:  # noqa: BLE001 — 한 날짜 실패가 나머지를 막지 않게
            logger.exception("monitor_snapshot: %s 스냅샷 실패", d)
            continue
        summary_days[d] = summary_entry(day)
        done.append(d)
        if d == yesterday:
            yesterday_day = day
    # 실패한 날짜가 있으면 백필 완료로 표시하지 않는다(다음 실행이 다시 시도).
    complete_after = complete_after and len(done) == len(targets)
    if done or complete_after != backfill_complete:
        _write_json_retry(
            gh, SUMMARY_PATH, {"days": summary_days, "backfill_complete": complete_after or backfill_complete},
            f"data: monitor summary +{len(done)}" + (f" ({done[0]}~{done[-1]})" if done else ""))
    if yesterday_day is None:
        # 이미 스냅샷돼 있던 경우(스케줄러 재시도) — 저장본을 그대로 쓴다.
        yesterday_day = read_day(gh, yesterday)
    return {"yesterday": yesterday_day, "yesterdayDate": yesterday,
            "snapshotted": done, "summary": summary_days}


# ── DM: "오늘의 멤버 현황" 텍스트 ────────────────────────────────────────────

def _rel_min(hm: str) -> int:
    """"HH:MM"(가상 "30:00" 포함) → 그날 06:00 기준 경과분. 프론트 minutesOf() 와 같음."""
    h, m = map(int, hm.split(":"))
    if h >= 24:
        return h * 60 + m - DAY_START_HOUR * 60
    return ((h * 60 + m) - DAY_START_HOUR * 60) % 1440


def _clock(rel: int) -> str:
    total = rel + DAY_START_HOUR * 60
    prefix = "익일 " if total >= 1440 else ""
    total %= 1440
    return f"{prefix}{total // 60:02d}:{total % 60:02d}"


def _live_ranges(segs: list[dict]) -> list[str]:
    out = []
    for sg in segs:
        if sg.get("s") != "live":
            continue
        a, b = _rel_min(sg["from"]), _rel_min(sg["to"])
        start = "06:00 이전부터" if sg.get("carried") else _clock(a)
        # "30:00" = 하루 끝까지 다음 전이가 없었음 — 그 시각에 끝났다는 뜻이 아니다.
        end = "익일 06:00 넘어서까지" if sg["to"] == "30:00" else _clock(b)
        dur = max(0, b - a)
        more = "+" if (sg.get("carried") or sg["to"] == "30:00") else ""
        out.append(f"{start}~{end} ({dur}분{more})")
    return out


def member_status_text(date_kst: str, day: dict | None) -> str:
    """웹 monitor "오늘의 멤버 현황" 패널(멤버별 트윗 수집 결과·라이브 구간 + 소식 등록)과
    같은 내용을 텔레그램 HTML 텍스트로."""
    head = f"📊 <b>멤버 현황 — {date_kst}</b> (06:00~익일 06:00 KST)"
    if day is None:
        return head + "\n⚠️ 이 날짜 모니터링 스냅샷을 만들지 못했습니다(백엔드 로그 확인 필요)."
    lines = [head]
    if not day.get("hasLog"):
        lines.append("⚠️ 이 날짜 이벤트 로그 파일이 없습니다 — 0건인지 기록 누락인지 구분할 수 없습니다.")
    preview = {v["member"]: v["segs"] for v in day.get("preview", [])}
    for m in monitor_report.MEMBER_ORDER:
        tw = [e for e in day.get("tweet", []) if e.get("member") == m]
        err = sum(1 for e in tw if e.get("tone") == "err")
        ok = len(tw) - err
        tweet = f"트윗 {len(tw)}건" + (f" (✓{ok}" + (f" ✕{err}" if err else "") + ")" if tw else "")
        ranges = _live_ranges(preview.get(m, []))
        live = ", ".join(ranges) if ranges else "—"
        lines.append(f"• <b>{html.escape(monitor_report.MEMBER_KO[m])}</b> · {tweet} · 라이브 {html.escape(live)}")
    notice = day.get("notice", [])
    n_err = sum(1 for e in notice if e.get("tone") == "err")
    lines.append(f"📰 소식 등록: 성공 {len(notice) - n_err} · 실패 {n_err} · 총 {len(notice)}건")
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # ── pending_dates ──
    assert pending_dates({}, "2026-09-22", ["2026-09-16", "2026-09-20", "2026-09-22", "2026-09-23"], False) == (
        ["2026-09-16", "2026-09-20", "2026-09-22"], True), "최초: 로그 파일 있는 과거 날짜만 + 전날"
    assert pending_dates({}, "2026-09-22", [], False) == (["2026-09-22"], True)
    assert pending_dates({"2026-09-19": {}}, "2026-09-22", None, True) == (
        ["2026-09-20", "2026-09-21", "2026-09-22"], True), "누락분 채움"
    assert pending_dates({"2026-09-22": {}}, "2026-09-22", None, True) == ([], True), "재시도 → 없음"
    many = [f"2026-08-{i:02d}" for i in range(1, 31)]
    got, complete = pending_dates({}, "2026-09-22", many, False)
    assert len(got) == MAX_PER_RUN and got[-1] == "2026-09-22" and got[0] == "2026-08-01" and not complete, got
    # 다음 실행: 앞서 채운 날짜는 빼고 이어서(전날 이후 날짜로 건너뛰지 않음)
    filled = {d: {} for d in got}
    got2, _ = pending_dates(filled, "2026-09-23", many, False)
    assert got2[0] == "2026-08-10" and got2[-1] == "2026-09-23", got2
    print("[OK] pending_dates: 최초 백필·누락분·재시도·상한·상한 뒤 이어하기")

    # ── summary_entry ──
    assert summary_entry({"hasLog": False}) == {"no_log": True}
    assert summary_entry({"hasLog": True, "backfillOnly": True, "eventCount": 4}) == {"backfill_only": True, "events": 4}
    d = {"hasLog": True, "ops": [{}], "ticks": [{}, {}], "relay": [], "notice": [{}],
         "tweet": [{"via": "ingest"}, {"via": "ops"}], "eventCount": 9}
    assert summary_entry(d) == {"triggers": 5, "events": 9}, "via=ops(수동)는 인입 트리거에서 제외"
    d_up = dict(d, upstream=[{}, {}, {}])
    assert summary_entry(d_up) == {"triggers": 6, "events": 9}, "업스트림 기록이 있으면 그 건수로"
    print("[OK] summary_entry")

    # ── _live_ranges: 자정 넘김·하루 끝·선행 구간 ──
    assert _live_ranges([{"s": "live", "from": "23:30", "to": "00:40"}]) == ["23:30~익일 00:40 (70분)"]
    assert _live_ranges([{"s": "live", "from": "21:00", "to": "30:00"}]) == ["21:00~익일 06:00 넘어서까지 (540분+)"]
    assert _live_ranges([{"s": "live", "from": "06:00", "to": "07:00", "carried": True}]) == ["06:00 이전부터~07:00 (60분+)"]
    assert _live_ranges([{"s": "upcoming", "from": "06:00", "to": "07:00"}]) == []
    print("[OK] _live_ranges")

    # ── member_status_text ──
    day = {
        "hasLog": True,
        "tweet": [{"member": "arale", "tone": "ok"}, {"member": "arale", "tone": "err"}],
        "preview": [{"member": "yuno", "segs": [{"s": "live", "from": "20:00", "to": "21:30"}]}],
        "notice": [{"tone": "ok"}],
    }
    txt = member_status_text("2026-09-22", day)
    assert "아라레</b> · 트윗 2건 (✓1 ✕1) · 라이브 —" in txt, txt
    assert "유노</b> · 트윗 0건 · 라이브 20:00~21:30 (90분)" in txt, txt
    assert "성공 1 · 실패 0 · 총 1건" in txt
    assert "로그 파일이 없습니다" in member_status_text("2026-09-22", {"hasLog": False})
    assert "만들지 못했습니다" in member_status_text("2026-09-22", None)
    print("[OK] member_status_text")

    # ── run_daily (gh mock): 최초 실행 백필 + 요약 1회 커밋 + 로그 없는 날 no_log ──
    class _Gh:
        def __init__(self, files):
            self.files = dict(files)
            self.writes = []
        def list_dir(self, path):
            return [p.split("/", 1)[1] for p in self.files if p.startswith(path + "/") and p.count("/") == 1]
        def read_text(self, path):
            return (self.files[path], "sha") if path in self.files else (None, None)
        def read_json(self, path):
            return (json.loads(self.files[path]), "sha") if path in self.files else (None, None)
        def write_json(self, path, data, *, prev_sha, message):
            self.files[path] = json.dumps(data)
            self.writes.append(path)
            return True, "sha2"

    ev = json.dumps({"ts": "2026-09-20T01:00:00Z", "flow": "tick", "result": "ok", "mode": "light"})
    gh = _Gh({"monitoring/events-2026-09-20.jsonl": ev + "\n", "monitoring/latest.html": "x"})
    r = run_daily(gh, today_bucket="2026-09-23", now_iso="2026-09-22T21:10:00Z",
                  healthchecks_api_key="", healthchecks_uuid="", vercel_token="")
    assert r["snapshotted"] == ["2026-09-20", "2026-09-22"], r["snapshotted"]
    assert r["summary"]["2026-09-20"] == {"triggers": 1, "events": 1}
    assert r["summary"]["2026-09-22"] == {"no_log": True}, "전날 로그 없음 → 숫자 대신 no_log"
    assert "2026-09-21" not in r["summary"], "로그 파일도 없고 최초 백필 대상도 아닌 날은 만들지 않음"
    assert gh.writes.count(SUMMARY_PATH) == 1
    assert json.loads(gh.files[SUMMARY_PATH])["backfill_complete"] is True
    snap = json.loads(gh.files["monitoring/days/2026-09-20.json"])
    assert snap["downRanges"] is None and snap["vercelDeploys"] is None, "키 없음 → 확인 불가(None)"
    assert snap["snapshotAt"] == "2026-09-22T21:10:00Z"
    # 재시도: 이미 있음 → 새 스냅샷 없이 저장본 반환
    gh.writes.clear()
    r2 = run_daily(gh, today_bucket="2026-09-23", now_iso="2026-09-22T21:15:00Z",
                   healthchecks_api_key="", healthchecks_uuid="", vercel_token="")
    assert r2["snapshotted"] == [] and gh.writes == [] and r2["yesterday"]["date"] == "2026-09-22"
    print("[OK] run_daily: 최초 백필·no_log·요약 1회 커밋·재시도 멱등")

    print("\nSUCCESS: monitor_snapshot.py self-test 통과 (mock)")
