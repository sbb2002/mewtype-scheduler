"""`/monitor` — 실제 모니터링 이벤트 로그(monitor_log.py가 append한 JSONL)를 하루치(또는
`--full`로 이번 달 전체) 모아 Ops Timeline 대시보드 html로 렌더링. push_monitor.py(git
커밋 기반 Vercel 한도 감시)를 대체한다(v3.5, 2026-09-16 세션에서 확정한 1~3단계 스키마
그대로 소비). 하루 경계는 KST 00:00 이 아니라 **06:00~익일 06:00**(v3.5.1) — 자정 넘겨
방송하는 멤버가 흔해서.

여러 날짜 브라우징(잔디 클릭, v3.5.1)은 `full=True`(`/monitor --full`)일 때만 — 이번 달
1일~오늘 전부를 한 리포트에 담아 클라이언트 쪽 전환만으로 날짜를 바꾼다(재요청 없음).
인자 없는 `/monitor`·`--auto` 자동 실행은 계속 하루치만(가벼움 유지).

이 리포트는 실데이터만 다루므로, 같은 세션에서 만든 Artifact 목업에 있던 아래 기능은
뺐다 — 전부 "재현 근거 데이터가 없어서" 뺀 것이지 귀찮아서가 아니다:
  - 트리거→결과 인과관계 점선 — "이 tick이 이 전이를 일으켰다"를 실제로 연결할
    근거가 로그에 없다(추론하면 틀릴 수 있음).
  - 트윗 말풍선/영상 썸네일 미리보기 — 로그에 원문 텍스트·썸네일 URL을 안 남겼다
    (중복 저장 방지). detail(= 원본 mode 문자열)만 툴팁에 표시.

self-test: python -m src.backend.monitor_report
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import requests

from .monitor_log import DAY_START_HOUR, bucket_date_kst

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
MEMBER_ORDER = ["arale", "yuno", "nonoka", "ritsu", "miyako"]
MEMBER_KO = {"arale": "아라레", "yuno": "유노", "nonoka": "노노카", "ritsu": "리츠", "miyako": "미야코"}


def _kst_hm(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST)
    return dt.strftime("%H:%M")


def _add_minutes(hm: str, minutes: int) -> str:
    h, m = map(int, hm.split(":"))
    total = (h * 60 + m + minutes) % (24 * 60)
    return f"{total // 60:02d}:{total % 60:02d}"


def parse_events(text: str) -> list[dict]:
    """JSONL 텍스트 → 이벤트 dict 리스트. 손상된 줄은 건너뛴다(전체를 죽이지 않음)."""
    events = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            logger.warning("monitor_report: 손상된 줄 건너뜀: %r", line[:120])
    return events


def _group(events: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {"tick": [], "ops": [], "notice": [], "tweet": [], "relay": [], "preview": []}
    for e in events:
        flow = e.get("flow")
        key = "tick" if flow in ("tick", "wake") else flow
        if key in out:
            out[key].append(e)
    return out


def _ticks_json(events: list[dict]) -> list[dict]:
    out = []
    for e in sorted(events, key=lambda x: x["ts"]):
        kind = "wake" if e.get("flow") == "wake" else "tick"
        out.append({
            "t": _kst_hm(e["ts"]), "kind": kind, "mode": e.get("mode", kind),
            "ok": e.get("result") != "err", "quota": e.get("quota") or 0, "d": e.get("detail", ""),
        })
    return out


def _ops_json(events: list[dict]) -> list[dict]:
    return [
        {"t": _kst_hm(e["ts"]), "cmd": e.get("who", ""), "ok": e.get("result") != "err", "d": e.get("detail", "")}
        for e in sorted(events, key=lambda x: x["ts"])
    ]


def _tone_json(events: list[dict]) -> list[dict]:
    """notice/relay 공용 — 헤드라인을 안 남겨서 tone/detail만."""
    return [
        {"t": _kst_hm(e["ts"]), "tone": e.get("result", "ok"), "d": e.get("detail", "")}
        for e in sorted(events, key=lambda x: x["ts"])
    ]


def _tweet_json(events: list[dict]) -> list[dict]:
    return [
        {"t": _kst_hm(e["ts"]), "member": e.get("who", ""), "tone": e.get("result", "ok"), "d": e.get("detail", "")}
        for e in sorted(events, key=lambda x: x["ts"])
    ]


def _preview_json(events: list[dict], now_hm: str | None) -> list[dict]:
    """멤버별로 그날 있었던 상태 전이를 이어붙여 Gantt 세그먼트로. 순수 함수."""
    by_member: dict[str, list[dict]] = {m: [] for m in MEMBER_ORDER}
    for e in sorted(events, key=lambda x: x["ts"]):
        ck = e.get("who")
        if ck in by_member:
            by_member[ck].append(e)

    out = []
    for member in MEMBER_ORDER:
        evs = by_member[member]
        segs: list[dict] = []
        title = None
        if evs and evs[0].get("from_state"):
            # "06:00" = 이 리포트가 다루는 하루의 시작(DAY_START_HOUR) — 그 전이가 관측되기
            # 전부터 이미 이 상태였다고 가정.
            segs.append({"s": evs[0]["from_state"], "from": "06:00", "to": _kst_hm(evs[0]["ts"])})
        for i, e in enumerate(evs):
            to_state = e.get("to_state")
            title = e.get("title") or title
            seg_from = _kst_hm(e["ts"])
            if i + 1 < len(evs):
                seg_to = _kst_hm(evs[i + 1]["ts"])
            elif to_state == "none":
                seg_to = _add_minutes(seg_from, 3)  # 사라짐은 짧게 표시(실제로 관찰 구간이 없으므로)
            else:
                # "30:00" = 이 하루의 끝(다음날 06:00) — 프론트 minutesOf()가 이 가상 시각을
                # 앵커 변환 없이 그대로 받아들여 차트 맨 끝에 고정한다.
                seg_to = now_hm or "30:00"
            seg = {"s": to_state, "from": seg_from, "to": seg_to}
            if e.get("result") and e["result"] != "ok":
                seg["q"] = e["result"]
                seg["qd"] = e.get("detail", "")
            # (v3.8.4 item 10) "방송 중 추정"(assumed_live) — announced/upcoming 상태값과
            # 별개로 프론트가 빨강 빗금으로 덮어 그리는 데 쓴다. 선행 세그먼트(위 121번 줄,
            # 관측 전 06:00부터 있었다고 가정하는 구간)는 근거 이벤트가 없어 대상에서 뺀다.
            if e.get("assumed_live"):
                seg["assumed_live"] = True
            segs.append(seg)
        out.append({"member": member, "title": title, "segs": segs})
    return out


def _day_bounds(date_kst: str) -> tuple[datetime, datetime]:
    """date_kst(YYYY-MM-DD) → 이 리포트가 다루는 "하루"의 [시작,끝) — 06:00 KST~익일 06:00 KST."""
    start = datetime.strptime(date_kst, "%Y-%m-%d").replace(tzinfo=KST) + timedelta(hours=DAY_START_HOUR)
    return start, start + timedelta(days=1)


def _fetch_health_down_ranges(api_key: str, uuid: str, date_kst: str) -> list[dict]:
    """healthchecks.io flips(up/down 이력)에서 이 날짜(06:00 KST~익일 06:00 KST)의 다운 구간만
    HH:MM 범위로 변환. 키/uuid 없거나 조회 실패하면 빈 리스트(=하루 종일 정상으로 렌더) — 조용히 성능저하."""
    if not api_key or not uuid:
        return []
    day_start, day_end = _day_bounds(date_kst)
    try:
        resp = requests.get(
            f"https://healthchecks.io/api/v3/checks/{uuid}/flips/",
            headers={"X-Api-Key": api_key},
            params={
                "start": int(day_start.astimezone(timezone.utc).timestamp()),
                "end": int(day_end.astimezone(timezone.utc).timestamp()),
            },
            timeout=10,
        )
        resp.raise_for_status()
        flips = resp.json().get("flips", [])
    except Exception as e:  # noqa: BLE001
        logger.warning("monitor_report: healthchecks.io flips 조회 실패: %s", e)
        return []

    flips.sort(key=lambda f: f["timestamp"])
    ranges: list[dict] = []
    down_since = None
    for f in flips:
        hm = _kst_hm(f["timestamp"])
        if f.get("up") == 0:
            down_since = hm
        elif down_since is not None:
            ranges.append({"from": down_since, "to": hm})
            down_since = None
    if down_since is not None:
        ranges.append({"from": down_since, "to": "30:00"})  # 프론트 anchor 기준 "하루의 끝"
    return ranges


def _vercel_push_count(github_token: str, date_kst: str) -> int:
    """그날(06:00 KST~익일 06:00 KST) main 브랜치 push 횟수 — push_monitor.py의
    fetch_commits(이미 검증된 코드) 재사용."""
    if not github_token:
        return 0
    from .push_monitor import _CODE_REPO, fetch_commits

    day_start, day_end = _day_bounds(date_kst)
    since = day_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        commits = fetch_commits(github_token, _CODE_REPO, "main", since)
    except Exception as e:  # noqa: BLE001
        logger.warning("monitor_report: vercel push count 조회 실패: %s", e)
        return 0
    cnt = 0
    for c in commits:
        try:
            ts = datetime.fromisoformat((c.get("date") or "").replace("Z", "+00:00")).astimezone(KST)
        except ValueError:
            continue
        if ts < day_end:
            cnt += 1
    return cnt


def _month_dates(end_date_kst: str) -> list[str]:
    """end_date_kst가 속한 달의 1일부터 end_date_kst까지 날짜 문자열 목록(오름차순)."""
    end = datetime.strptime(end_date_kst, "%Y-%m-%d")
    d = end.replace(day=1)
    out = []
    while d <= end:
        out.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)
    return out


def _build_day(
    gh, date_kst: str, *, now_hm: str | None,
    healthchecks_api_key: str, healthchecks_uuid: str, github_token_for_commits: str,
) -> dict:
    """하루치(06:00 KST~익일 06:00 KST) 이벤트 로그 + healthchecks.io + 커밋 수를 모은다."""
    text, _sha = gh.read_text(f"monitoring/events-{date_kst}.jsonl")
    events = parse_events(text)
    grouped = _group(events)
    return {
        "ticks": _ticks_json(grouped["tick"]),
        "ops": _ops_json(grouped["ops"]),
        "notice": _tone_json(grouped["notice"]),
        "relay": _tone_json(grouped["relay"]),
        "tweet": _tweet_json(grouped["tweet"]),
        "preview": _preview_json(grouped["preview"], now_hm),
        "downRanges": _fetch_health_down_ranges(healthchecks_api_key, healthchecks_uuid, date_kst),
        "vercelPush": _vercel_push_count(github_token_for_commits, date_kst),
        "eventCount": len(events),
    }


def build_report(
    gh, *, date_kst: str | None = None, full: bool = False,
    healthchecks_api_key: str = "", healthchecks_uuid: str = "",
    github_token_for_commits: str = "",
) -> dict:
    """오늘(또는 date_kst)치, `full=True`면 이번 달 1일~오늘치 전부를 모아 REPORT dict로.
    gh는 data 저장소용 GitHubStore(text 읽기). 하루 경계는 06:00 KST~익일 06:00 KST."""
    now_kst = datetime.now(KST)
    today_bucket = bucket_date_kst(now_kst)
    date_kst = date_kst or today_bucket
    dates = _month_dates(today_bucket) if full else [date_kst]

    days = {
        d: _build_day(
            gh, d, now_hm=(now_kst.strftime("%H:%M") if d == today_bucket else None),
            healthchecks_api_key=healthchecks_api_key, healthchecks_uuid=healthchecks_uuid,
            github_token_for_commits=github_token_for_commits,
        )
        for d in dates
    }
    selected = date_kst if date_kst in days else today_bucket

    return {
        "date": selected,
        "full": full,
        "month": dates,
        "days": days,
        "eventCount": days[selected]["eventCount"],
    }


def run(
    gh, *, date_kst: str | None = None, full: bool = False,
    healthchecks_api_key: str = "", healthchecks_uuid: str = "",
    github_token_for_commits: str = "",
) -> dict:
    """`_handle_monitor`/`/monitor` Flask 라우트 진입점. {"html", "date", "events"} 반환."""
    report = build_report(
        gh, date_kst=date_kst, full=full, healthchecks_api_key=healthchecks_api_key,
        healthchecks_uuid=healthchecks_uuid, github_token_for_commits=github_token_for_commits,
    )
    return {"html": render_html(report), "date": report["date"], "events": report["eventCount"]}


def render_html(report: dict) -> str:
    return _TEMPLATE.replace("__REPORT_JSON__", json.dumps(report, ensure_ascii=False))


_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Monitor</title>
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap">
<style>
  :root{
    color-scheme:dark;
    --bg:#0d0e12; --panel:#15161a; --panel-2:#1a1c22; --line:#2a2c33; --line-soft:#21232a;
    --ink:#e8e8e8; --muted:#8a8f98; --muted-2:#5f6570; --accent:#7dd3c0;
    --ok:#7CB342; --err:#e5484d;
    /* (v3.8.4 item 10) live 미만 등급은 노랑 계열 그라데이션 — 낮은 확신도일수록 어둡게.
       watching 은 upcoming 과 같은 노랑 바탕에 빗금(패턴)으로 구분. */
    --st-announced:#8a6d1a; --st-upcoming:#f5c344; --st-watching:#f5c344;
    --st-live:#ff5470; --st-live-assumed:#ff5470; --st-end:#575757; --st-none:#424242;
    --mono:"JetBrains Mono",ui-monospace,"SF Mono",Consolas,monospace;
    --sans:-apple-system,"Segoe UI",Inter,sans-serif;
  }
  *{box-sizing:border-box}
  body{margin:0; background:var(--bg); color:var(--ink); font:14px/1.55 var(--sans);
       padding:28px 20px 60px; max-width:1280px; margin-inline:auto}
  h1{font-size:1.5rem; margin:0 0 4px; letter-spacing:-.01em}
  .lede{color:var(--muted); font-size:.86rem; max-width:70ch; margin:0 0 18px}
  .lede b{color:var(--ink); font-weight:600}

  .tabs{display:flex; gap:4px; margin-bottom:18px; border-bottom:1px solid var(--line)}
  .tab-btn{font:600 .82rem var(--sans); color:var(--muted); background:none; border:none;
    border-bottom:2px solid transparent; padding:9px 4px; margin-bottom:-1px; cursor:pointer}
  .tab-btn + .tab-btn{margin-left:14px}
  .tab-btn:hover{color:var(--ink)}
  .tab-btn.active{color:var(--ink); border-bottom-color:var(--accent)}
  .ext-gauge-row{display:grid; grid-template-columns:repeat(2,1fr); gap:10px; margin-bottom:16px}
  @media (max-width:520px){.ext-gauge-row{grid-template-columns:1fr}}

  section{margin-bottom:26px}
  .panel{background:var(--panel); border:1px solid var(--line); border-radius:12px; padding:18px 20px}
  h2{font-size:.98rem; margin:0 0 3px; font-weight:600}
  .panel-sub{color:var(--muted); font-size:.78rem; margin:0 0 14px}

  .stats-row{display:grid; grid-template-columns:repeat(4,1fr); gap:10px}
  .stat-tile{background:var(--panel); border:1px solid var(--line); border-radius:10px; padding:13px 14px; min-width:0}
  .stat-tile b{display:block; font:600 1.5rem/1.2 var(--mono); font-variant-numeric:tabular-nums; margin-bottom:3px;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
  .stat-tile span{color:var(--muted); font-size:.72rem}
  .stat-tile.error b{color:var(--err)}
  @media (max-width:720px){.stats-row{grid-template-columns:repeat(2,1fr)}}

  /* (v3.5.5) 오늘의 멤버 현황 — 왼쪽(멤버 5행) + 오른쪽(기존 4항목 세로 목록)을
     하나의 직사각형 패널로. */
  .combo{background:var(--panel); border:1px solid var(--line); border-radius:12px;
    display:grid; grid-template-columns:1fr 176px; overflow:hidden}
  .combo h2{font-size:.86rem; margin:0 0 3px}
  .combo-left{padding:16px 18px}
  .combo-right{padding:16px 16px; border-left:1px solid var(--line); display:flex; flex-direction:column}
  .combo .panel-sub{font-size:.7rem; margin:0 0 12px}

  .member-grid{display:flex; flex-direction:column}
  .m-row{display:flex; align-items:center; gap:8px; padding:6px 0; border-top:1px solid var(--line-soft)}
  .m-row:first-child{border-top:none}
  .m-who{display:flex; align-items:center; gap:7px; min-width:0; flex:none}
  .m-who img{width:22px; height:22px; border-radius:6px; background:var(--panel-2); flex:none}
  .m-who span{font-size:.76rem; color:var(--ink); font-weight:500; white-space:nowrap}
  .m-tweet{font-size:.72rem; color:var(--muted); font-family:var(--mono); white-space:nowrap; margin-left:auto; padding-left:8px}
  .m-tweet b{font:600 .78rem var(--mono); color:var(--ink); margin-right:4px}
  .m-tweet .ok{color:var(--ok)}
  .m-tweet .err{color:var(--err)}
  .live-dot{width:7px; height:7px; border-radius:50%; margin-left:8px; flex:none}
  .live-dot.on{background:var(--st-live); box-shadow:0 0 0 3px color-mix(in srgb, var(--st-live) 20%, transparent)}
  .live-dot.off{background:var(--line); border:1px solid var(--muted-2)}

  .notice-line{display:flex; align-items:center; justify-content:space-between; margin-top:12px;
    padding-top:11px; border-top:1px solid var(--line-soft)}
  .notice-line .label{font-size:.76rem; color:var(--ink); font-weight:500}
  .notice-line .figures{font:500 .72rem var(--sans); color:var(--muted); display:flex; gap:10px}
  .notice-line .figures b{font:600 .82rem var(--mono); color:var(--ink); font-variant-numeric:tabular-nums; margin-right:2px}
  .notice-line .figures .ok b{color:var(--ok)}
  .notice-line .figures .err b{color:var(--err)}

  .stat-list{display:flex; flex-direction:column; flex:1; justify-content:space-between}
  .stat-item + .stat-item{border-top:1px solid var(--line-soft)}
  .stat-item{padding:9px 0}
  .stat-item b{display:block; font:600 1.15rem/1.2 var(--mono); font-variant-numeric:tabular-nums; margin-bottom:2px;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
  .stat-item span{color:var(--muted); font-size:.66rem; line-height:1.3; display:block}
  .stat-item.error b{color:var(--err)}

  @media (max-width:640px){
    .combo{grid-template-columns:1fr}
    .combo-right{border-left:none; border-top:1px solid var(--line)}
    .stat-list{flex-direction:row; flex-wrap:wrap; gap:0 18px}
    .stat-item{flex:1 1 40%; border-top:none !important}
  }

  .grass{display:flex; flex-wrap:wrap; gap:5px}
  .grass button{width:26px; height:26px; border-radius:6px; border:2px solid transparent; padding:0;
    font:600 11px var(--mono); cursor:pointer; font-variant-numeric:tabular-nums}
  .grass button.sel{border-color:var(--ink)}
  .grass button:hover{filter:brightness(1.2)}
  .grass button.future{cursor:default; opacity:.35}

  .legend{display:flex; flex-wrap:wrap; gap:6px}
  .legend button{display:inline-flex; align-items:center; gap:6px; font:500 .74rem var(--sans); color:var(--ink);
    background:var(--panel-2); border:1px solid var(--line); border-radius:7px; padding:4px 9px 4px 8px; cursor:pointer}
  .legend button:hover{border-color:var(--muted)}
  .legend button.off{opacity:.3}
  .legend button i{width:9px; height:9px; border-radius:50%; flex:none}

  .tl-toolbar{display:flex; align-items:center; gap:10px; margin-bottom:10px; flex-wrap:wrap}
  .tl-zoom{display:inline-flex; align-items:center; gap:2px; background:var(--panel-2); border:1px solid var(--line);
    border-radius:8px; padding:3px}
  .tl-zoom button{width:26px; height:26px; border:none; background:none; color:var(--ink); font:600 14px var(--mono);
    border-radius:6px; cursor:pointer}
  .tl-zoom button:hover{background:var(--line)}
  .tl-zoom span{font:600 11px var(--mono); color:var(--muted); width:38px; text-align:center; font-variant-numeric:tabular-nums}
  .tl-hint{color:var(--muted-2); font-size:.72rem}
  .tl-body{display:flex; align-items:stretch}
  .tl-labels{position:relative; flex:0 0 50px; border-right:1px solid var(--line); padding-right:2px}
  /* (v3.8.4-후속, item 3) 그룹 아이콘을 뱃지(배경·테두리 박스)로 — 아래 스파인(grp-spine)이
     이 뱃지에서 뻗어나와 하위 멤버 뱃지(.row img)들을 관통하며 "이 그룹 소속" 임을 보여준다. */
  .tl-labels .grp{position:absolute; left:2px; width:24px; height:24px; transform:translateY(-50%);
    display:flex; align-items:center; justify-content:center; font-size:15px; line-height:1; cursor:pointer;
    opacity:.92; background:var(--panel-2); border:1px solid var(--line); border-radius:7px; z-index:2}
  .tl-labels .grp:hover{opacity:1; filter:brightness(1.25); border-color:var(--muted)}
  .tl-labels .grp-spine{position:absolute; left:12px; width:3px; background:var(--line); border-radius:2px; z-index:0}
  .tl-labels .row{position:absolute; left:28px; right:2px; transform:translateY(-50%); text-align:center; z-index:1}
  .tl-labels .row img{width:16px; height:16px; border-radius:4px; vertical-align:middle; background:var(--panel-2);
    border:1px solid var(--line-soft); padding:1.5px}
  .tl-scroll{position:relative; overflow-x:auto; overflow-y:hidden; border-radius:0 8px 8px 0; flex:1; min-width:0;
    touch-action:none; cursor:grab}
  .tl-scroll.dragging{cursor:grabbing}
  .tl-scroll.locked{overflow:hidden; cursor:default}
  #tlSvg{display:block}
  .tl-crosshair{position:absolute; top:0; width:1px; background:rgba(255,255,255,.35); pointer-events:none; display:none; z-index:5}
  .tl-lane{stroke:var(--line); stroke-width:1}
  .tl-hour{stroke:var(--line-soft); stroke-width:1}
  .tl-hour-label{fill:var(--muted-2); font:10px var(--mono)}
  .tl-dot{cursor:pointer; stroke:var(--bg); stroke-width:1.5; transition:r .16s ease, cy .16s ease}
  .tl-dot:hover{stroke:var(--ink)}
  .tl-dot.dim{opacity:.15}
  /* (후속) 트리거 = 짧은 세로 히스토그램 막대 (점 대체) */
  .tl-trigger-bar{cursor:pointer; transition:height .16s ease, y .16s ease}
  .tl-trigger-bar:hover{filter:brightness(1.25)}
  .tl-trigger-bar.dim{opacity:.15}
  .tl-seg{cursor:pointer}
  .tl-seg:hover{filter:brightness(1.25)}

  .tooltip{position:fixed; background:#1c1e24; border:1px solid var(--line); border-radius:8px;
    padding:9px 11px; font-size:.76rem; pointer-events:auto; z-index:50; display:none;
    box-shadow:0 8px 24px rgba(0,0,0,.45); max-width:280px}
  .tooltip .tt-h{color:var(--muted); font:11px var(--mono); margin-bottom:5px}
  .tooltip .tt-title{font-size:.82rem; color:var(--ink); margin-bottom:3px; font-weight:600}
  .tooltip .tt-raw{font-family:var(--mono); font-size:.76rem; margin-bottom:3px}
  .tooltip .tt-raw.ok{color:var(--ok)} .tooltip .tt-raw.err{color:var(--err)} .tooltip .tt-raw.degraded{color:#f5c344}
  .tooltip .tt-d{color:var(--muted)}
  .lg-title{font-size:.85rem; font-weight:600; color:var(--ink); margin-bottom:4px}
  .lg-sub{color:var(--muted); font-size:.74rem; margin-bottom:8px; line-height:1.4}
  .lg-chips{display:flex; flex-wrap:wrap; gap:6px 12px; margin-bottom:8px}
  .lg-chip{display:inline-flex; align-items:center; gap:5px; font-size:.74rem; color:var(--ink)}
  .lg-chip i{width:11px; height:11px; border-radius:3px; flex:none}
  .lg-note{color:var(--muted-2); font-size:.7rem; line-height:1.45; padding-top:7px; border-top:1px solid var(--line-soft)}

  .ev-table{width:100%; border-collapse:collapse; font-size:.8rem}
  .ev-table th,.ev-table td{padding:7px 9px; border-bottom:1px solid var(--line-soft); text-align:left; vertical-align:top}
  .ev-table th{color:var(--muted); font-weight:500; font-size:.72rem; text-transform:uppercase; letter-spacing:.03em}
  .ev-table td.t-time{font-family:var(--mono); font-variant-numeric:tabular-nums; white-space:nowrap; color:var(--muted)}
  .ev-table td.t-who{white-space:nowrap}
  .ev-table td.t-raw{font-family:var(--mono); font-size:.78rem}
  .ev-table td.t-detail{color:var(--muted)}
  .ev-table tr.filtered{display:none}
  .ev-table tr.flash{animation:flash 1.1s ease}
  @keyframes flash{0%{background:rgba(125,211,192,.18)}100%{background:transparent}}
  .dot-swatch{display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:7px; vertical-align:1px}
  .ev-scroll{overflow-x:auto}
  @media (max-width:640px){.ev-table{min-width:640px}}

  footer{color:var(--muted-2); font-size:.74rem; margin-top:8px; text-align:center}
</style>
</head>
<body>
<h1>Monitor</h1>
<p class="lede" id="lede">불러오는 중…</p>

<section class="panel" id="grassPanel" hidden>
  <h2>월간 추이</h2>
  <p class="panel-sub">날짜 칸을 누르면 아래 전체가 그 날짜로 바뀝니다. 하루 기준은 06:00~익일 06:00(KST) —
    자정 넘겨 이어지는 방송을 하루로 묶기 위함.</p>
  <div class="grass" id="grass"></div>
</section>

<div class="tabs" role="tablist">
  <button class="tab-btn active" id="tabBtnApp" role="tab" aria-selected="true">APP</button>
  <button class="tab-btn" id="tabBtnExt" role="tab" aria-selected="false">EXT</button>
</div>

<div id="tabApp">
<section class="combo" id="combo">
  <div class="combo-left">
    <h2>오늘의 멤버 현황</h2>
    <p class="panel-sub">개인 트윗 수집 결과 · 이 날짜 안 라이브 진입 여부</p>
    <div class="member-grid" id="memberGrid"></div>
    <div class="notice-line" id="noticeLine"></div>
  </div>
  <div class="combo-right">
    <h2>요약</h2>
    <div class="stat-list" id="statList"></div>
  </div>
</section>

<section class="panel">
  <h2 id="tlTitle">—</h2>
  <p class="panel-sub" id="tlSub"></p>
  <div class="tl-toolbar">
    <div class="tl-zoom">
      <button id="zoomOut" aria-label="축소">－</button>
      <span id="zoomLabel">100%</span>
      <button id="zoomIn" aria-label="확대">＋</button>
    </div>
    <button class="tl-zoom" id="zoomReset" style="padding:0 10px; height:26px; font-size:.72rem; color:var(--muted)">리셋</button>
    <div class="legend" id="legend"></div>
    <span class="tl-hint">왼쪽 줄 이름을 누르면(PC는 호버) 그 줄 범례 · 차트 위 휠로 확대·축소</span>
  </div>
  <div class="tl-body">
    <div class="tl-labels" id="tlLabels"></div>
    <div class="tl-scroll" id="tlScroll"><svg id="tlSvg"></svg><div class="tl-crosshair" id="tlCrosshair"></div></div>
  </div>
</section>

<section class="panel">
  <h2>원본 이벤트 로그</h2>
  <p class="panel-sub">시각순 전체 기록 — result는 "성공/실패" 요약이 아니라 각 흐름이 실제로 반환한 원본 상태/문자열 그대로.</p>
  <div class="ev-scroll">
    <table class="ev-table" id="evTable">
      <thead><tr><th style="width:70px">시각</th><th style="width:150px">흐름</th><th style="width:110px">대상</th><th style="width:170px">raw 값</th><th>detail</th></tr></thead>
      <tbody id="evBody"></tbody>
    </table>
  </div>
</section>

<footer id="footer"></footer>
</div>

<div id="tabExt" hidden>
  <section class="panel">
    <h2>YouTube Data API quota</h2>
    <p class="panel-sub">정기수집·라이브감지 트리거(🕒/📡) 중 변화가 있어 기록된 실행의 quota 누적 — 변화 없는 실행은 기록하지 않으므로 실제 사용량은 GCP 콘솔 기준.</p>
    <div class="ext-gauge-row">
      <div class="stat-tile"><b id="extYtUsed">—</b><span>누적 사용량 / 10,000</span></div>
      <div class="stat-tile"><b id="extYtCalls">—</b><span>API 호출 수(기록된 실행)</span></div>
    </div>
    <div class="tl-scroll"><svg id="extYtChart" viewBox="0 0 900 120"></svg></div>
  </section>

  <section class="panel">
    <h2>Vercel Hobby 배포 한도</h2>
    <p class="panel-sub">data 브랜치 분리(v3.4.11) 이후엔 main/devpapers/기타 브랜치 push만 카운트됨.</p>
    <div class="ext-gauge-row">
      <div class="stat-tile" id="extVercelTile"><b id="extVercelUsed">—</b><span>push 횟수 / 100</span></div>
      <div class="stat-tile"><b id="extVercelStatus">—</b><span>상태</span></div>
    </div>
  </section>
</div>

<div class="tooltip" id="tooltip"></div>

<script>
const REPORT = __REPORT_JSON__;

const STATE = {
  announced:{ label:"예고(announced)",  color:"var(--st-announced)" },
  upcoming: { label:"예정(upcoming)",   color:"var(--st-upcoming)" },
  watching: { label:"대기(watching)",   color:"var(--st-watching)" },
  live:     { label:"방송 중(live)",    color:"var(--st-live)" },
  end:      { label:"방송 종료(end)",   color:"var(--st-end)" },
  none:     { label:"사라짐(none)",     color:"var(--st-none)" },
};
// (v3.8.4 item 9) sg.s 가 비어 있으면(과거 데이터 — from_state/to_state 필드 누락 버그가
// 고쳐지기 전에 기록된 이벤트) 'null' 문자열이 그대로 노출되던 것 방지. 새로 기록되는
// 이벤트는 항상 값이 있다(handlers.py/telegram_app.py 쪽 수정).
function stateLabel(s){ return (STATE[s] || {}).label || "상태 미상"; }
const OK = "#7CB342", ERR = "#e5484d", DEGRADED = "#f5c344";
const TONE_COLOR = { ok:OK, degraded:DEGRADED, err:ERR };
const TONE_LABEL = { ok:"정상", degraded:"부분 실패", err:"에러" };
const MEMBER_KO = { arale:"아라레", yuno:"유노", nonoka:"노노카", ritsu:"리츠", miyako:"미야코" };
// (v3.5.4) 타임라인 라벨 서브칸 -- 텍스트("노노카" 등) 대신 멤버 얼굴 도트아이콘(누끼딴
// 40x40 PNG, base64). 텍스트보다 폭이 좁아 라벨 칸 전체 폭을 줄일 수 있다.
const MEMBER_ICON = { ritsu:"data:image/png;base64,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", yuno:"data:image/png;base64,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", arale:"data:image/png;base64,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", miyako:"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAACgAAAAoCAYAAACM/rhtAAAMLklEQVR42s1Ye1BbVRr/nQu5eQkJgSZkCY8SoFYNtV2GTVsrliIysg3TKiKl9uGqWzslbde3HcXq1o7jgz7cXbftuKOVQXyUbWurdqlYtRIjC4WIttYokGBKSiFQyONGcvcPeq6XFDr6z47fnUzuveec7/zO974fISAQE8dx6lhWMsyA8PgNEBP9gmVZHwPCR8CT/xeIams1Ey0k4YFEXWEurA5zYTV9BtYz/Ht8zFt1b8bzNTXMVHP5Gp6Z+NVc+vEMHbNarczl82uYMBdWr8d6huDKFwgI6MSVpSvq11ruH11ruX/0rbo346dbdKWxqa7oQ081Xryg5EB2cs6BlaUr6uncMBdWE6vVyuzetTtSVVpZP+pS3eEe8AAABkM9oRjJ2AcA8OWXJxuUOvWH1ASmVMUViK6Jns+yrC8rOfvAtdolZeL3CRkI7Hlnl4FlWR+hTjIz8Xp/bopZqpUbAQDegBMA4B7wwJSnDwDAiZM2pmChOVL7t6f/lJCqbaCHmg4YXbvnnV0GAHh+w+NOu21ULR43JOkBAOJ9O/tsoR8unFIAgAAwKzn7gIq5puyuW5eRU16bX9JvlMepFQAAp8cxiaF7wIPBUE8oN8UsjQYEQNhU/H4w1BPSSNOl4nGt3Ig4tULgv21DCba8/AG6vMcPfnfu7HIAiI0+dVG+mi9CiXzLyx/AG5hgYtSbJoEEgKKsKikAxKkVuOjzAwCMJhMACM/0gABggF5K1wIQeLa5Jg69bUMJFDodATApvAkAx8PKElySh0KnI9s2lPBNdh9pttv4NtfPEqOqoOT0OAT1UGBUVeIDitXY5vpMkCoADPb1oMlulhXlT4AbDytLOI5TsyzrEwAuMM8+eLrdf0eT3UcsS3VQ6HRkYoGZ7D/ayOemmKVGvUkA0eb67GeUSdPboBsewAXMS73hZ4m6Jv4c9gYZnbthc61/52M2JjfFLC1YaI4IYZB6Mcdx6vtut7odrR75a0+thUKnI4cOn8HOxh3BaOdxD3hQYCpGXukMYimdc0UPPtE6gOOvnuJPOI4J9mvK0wdert2siJ5bsOhhfjDUEzrjsf+Oej4Jc2E1y7I+juPU5XnWC+4BD157ai2a7D4iBkeN2ag34em/F5ETrQMY7u+DSpcyLbjh/j4AgEqXgoK8JBw60oEtW58Nbqt5XJCcpXQODh3pwLGmj/zFRYWKLVufDYoBTnKSzj5bSCNNlx5s/cy3r7FJTr1O7MlpqUqyb3sLTnltfkerR/5L4qAhSY+z+WaizVWA8jzW9JH/xEkbYyltkNH78qq7AACNb7/7s4oJCKqt1czuXbsjayzrRh2tHjk1Xo00XWpI0kMrN062uUubim0ymqi9XfT5BbMQq7i4qFBBJQhAkCIA0CDNcZyaAYDdu3ZHso05N9MMQsHR+0l2YipGgakYWrlxWnAUGAUHAKY8fYCCdLR65MeaPvJT9Qr2etLGAMA/X/rHVpppCAHB6orVKz9p6thDgUVLSuwgi/PNBAB6XWO8GMxUdK1pBulynOevNc0glqWzcOjwGTTbbTzViClPH6DZiYITR5W6I/WVMWsq1qz8pKljT26KWaqLN8SO+EcnbZKVeL0ATis3IsgBKhVL3L3DkMokSEtVEq1OSc57/YhTKyCVSSCVSZCdrSaJ6hz09LrwI3EEylcVSuYtSsXQDyAf/vcYCkzF+NHtlfRfdI/3uNyECic7eXasLt4Q2/rNqawyyy09zE+jXKlGmi6lkqE0lXqptHpdY7w34ITT4xAkGadWIC1VSeaa5pK0VCXpcpzn2x3tPFUxpXsemw9Tnj5AIwJNl+K0SbGQgPwVxrLC8mcA2H+0kQeA8qybmPKsmxhxzqSbiFOXGHCX4zxP/9sd7XyX4zxPx9wDHmhCpknefr3WfBmjxflmctetywgANNttfG6KWbpu06onmYqqypGHn78zYTjy9cHOPluoxXcm0uI7E5mKgdPjmBJkNGBxuqMhasPmWj91CMvSWcJcat/NdhvfbLfxnX22EAA8tmPVQ+bCBS/FVlurmYqqypGGuvo1j1qfO0cn0NRG4582VwH3UY/AkHqkuFiYLgbWPrOa+Pv75RlLZk/wuk4jHICqme6rkaZLl1sLys2FCw5svnsvG2P/ws4DwPC50XqMJl1LjVQrN0Iqk0AyHoexn4Zwz7IbSZopndjtbRj7aQhlN91MZqYYSNuZNiTPMMB2thkxbBhKiUYAN/bTELZtKEGKOY2oM2dMsvHmL2yBoA8STZwOmjgdWMLGUic9dvwt6eDoYIOt/fA4AwDP1TyQPNgtK6OBdCp7016ngaV0Dhbnm0lnny2kzVVcplZxOPIGnEjIQCBjyexpP77ElZFWbhT2Hg8rS4Zc3gqO4yZK/vff+uAdFXNNWYGpGDSp0xKJBtvF+Ways3FHULzBxmWbhJza6xrjqTnQsv3l2s0Kmn+j1/W6xviLPv+kjENjo6PVI6eVeOzuXbsjWcnZl1XB4pTV5vKAllzilLX/aCNPPc/pcSAhA4EH/1givyQ1xb7tLZPWUaIRY17qDZftpwmZ5IYkYKgbcgCIWVOxZuWIK+7RucYFAIAerxPxijho4nTCoh6vE6Y8fWD7A6vZli+cqLinkIR6VIhhw+juc2PjuiVklbWQ3FoyXyK2tRdfeoefa1yA8o23kOGvCWLYMO61lpGs+CzSefY09Ko0SGWSiQ+wYBiekV5k6IwTeyd5A6c72ruYH13nlhuS9EhLVZIreaI4djXX9QhprvaZ1YR6ZTTVPrOaOD0O/PulzyeV8WL7jS4uaMU01A35v/bXVTD/+fzD5dFgqDrSUpWEOsA9j80XjPnGRQvJiqKljFZuhK3HNW2I8ff38wCwomgpc+OihWS+ehZDK5hok3J6HMK7RHUOEjIQAICY7OScA1xAfvXt6y1kfOAimZliIJ1nTyNRqodWpyRBDpCMx4GTBcm8G2bC/e0gCQQvoH/MDa1OSZbkZ0KpnbosVGfOIEM/gPSPuREIXkBsohyVd+fh0JEOdLX9gOQZBmGuo7sDZTfdTFQqlhgWaXDycGfsOZ93Zsym+9f7WWlM2blWPlalYgkAUPvQ6pREpWJJkAM+/eQL3HbnfGJIUGJIFoBSJ0Hl3XnTgqM0b1Eq3CODGOsPw7J0FpRaOep2fMVLxuOQna0mwyNhwc7nZE+EpMHvBzEscQduu/PmfTEff/7pt8ssJQ6Pr7vsmy537MwUA0mQpcF2thkJsjRkpl9HznnPQROnw+LSTMKGL/DX/D6HzMpJngSk+/g3PHUQ8T0AzMpJxrxFqcJhnJ39JMgBmenXEVZ6kRw6eQQFpmKoVCzpdY3xbWfakPuH5NUPPv3oC0y1tZqpef6vhxdbClYlZCCws3FHMNph5prmEgDYt70FkhTDlM6UsWQ2OXSkY1IBOhXt296CXtcYT3nSaigtVUl2Nu4IOj0OLLcWlG95/qmGy0r+ti9PvZKjkd+3YXOtnxaQG5dtkiWqcwAA7Y52Pi1VSajD/Frat70FzXYbvzjfTBLVObjg+xb7jzbytLSLVfvLFuTN1+3dv/e9Bx58YOTFF16MJwQE9COZNnjqX3+38KlHnnuDJm8ajAHglNfmd3kdysLc+YNleTeor5TKACDc5+Zfe91FDn+1l1zlN0XEdae4evnLQ2v3Vj+6cWP0eqE3QztP7x8+mf3q1gbbVD2XwVBPqGChOWJ9Yt0bu555ZeWJkzYmM1spv8pvigDAqMIxqWy/ym+KjCocTKrWNGZ9Yt0bj2x8RPvdmf4SOk4rJgAYlDoCiy0Fq2RyNJV/WzHKbGUiAkAeEULA8PTbOCEDAdo8SktVEmonJxzHJnWr6l9/t/CXqFYmR1NFVeVIVWll/ee2b8ooMMr7os+PsM4ZGOqG/O3WXYksy/qerIkwT29lIrETXVaG53E/c6lfd9Ci31SWaUrb0+E4fV+Xz8/TKC8OrpdM4sCvafMOOgegkaYLXQpaec8xXb2nxdOmTshQLZ1WxeKmJLXHyHuRmI+/7JYcdh2P1L56L9dQVx+/rPw2hmVZX0NdffyvcZCKqsoRjuPUjW+/G6moqhxZVfCq7PUTdwc/qvleVrg1Myg2M3GTFOQ3cIn72FP2qC97KWpuAzwBeELvr9Rr/iW9agpGzJPuORXv/wHxcQNhv2P3xgAAAABJRU5ErkJggg==", nonoka:"data:image/png;base64,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" };

let PREVIEW, TICKS, OPS, NOTICE, TWEET, RELAY, INGEST, TRIGGER_GROUPS, BACKEND_SEGS, CURRENT_DAY;

function computeIngest(relay, notice, tweet){
  return [
    ...relay.map(e => ({ t:e.t, source:"공식(BDP_yumemita)", ok:e.tone!=="err", target:{lane:"relay", row:"account"} })),
    ...notice.map(e => ({ t:e.t, source:"공식(BDP_yumemita)", ok:e.tone!=="err", target:{lane:"notice", row:"notice"} })),
    ...tweet.map(e => ({ t:e.t, source:(MEMBER_KO[e.member]||e.member)+" 개인", ok:e.tone!=="err", target:{lane:"tweet", row:e.member} })),
  ];
}
const TRIGGER_PRIORITY = { ops:0, ingest:1, tick:2, wake:2 };
// (v3.8.4 item 8) 같은 시각(t)의 트리거 이벤트는 개수와 무관하게 점 하나로 합쳐서 그린다
// (예전엔 종류별로 세로로 늘어놓아 몰리면 겹쳐 보였다). 대신 그 시각에 몇 건이 뭉쳤는지를
// 점 "크기"로 나타내고, 실제 목록은 호버/클릭 상세에서 보여준다. 5건 이상은 크기를 고정해
// 무한정 커지지 않게 한다 — trigger 레인(rowH=110, 중심 기준 ±55px) 안에 호버 확대(active)
// 상태까지 포함해 항상 들어가야 하므로 반지름 상한을 넉넉히 여유 있게 잡음(최대 35 < 55).
// (후속) 점 대신 아주 짧은 세로 히스토그램 막대 — 길이(높이) 비교가 원 면적/반지름 비교보다
// 지각적으로 더 정확하다(데이터비주얼라이제이션 정석: length > area encoding). 폭은 고정,
// 높이만 개수로 스케일. rowH 도 이에 맞춰 더 짧게 줄였다(item 4, 아래 LANES).
const TRIGGER_BAR_W = 8;
const TRIGGER_BAR_H_STEPS = [10, 16, 22, 28, 34];  // count 1·2·3·4·5+ (쉬는 상태)
const TRIGGER_BAR_ACTIVE_RATIO = 1.4;               // 호버 시 살짝만 더 키움(과하게 안 자라게)
function triggerBarHeightBase(count){ return TRIGGER_BAR_H_STEPS[Math.min(Math.max(count,1),5) - 1]; }
function triggerBarHeightActive(count){ return Math.round(triggerBarHeightBase(count) * TRIGGER_BAR_ACTIVE_RATIO); }
// 같은 t(정확히 같은 분)의 ops/tick·wake/ingest 이벤트를 한 그룹으로 묶는다. 그룹 내에서는
// TRIGGER_PRIORITY 순으로 정렬해 대표 아이콘(맨 앞, 팝업 표시용)을 정한다 — 점 자체엔 더
// 이상 아이콘을 안 그린다(후속 수정: 팝업에 이미 다 나오므로 중복).
function groupTriggerEvents(ops, ticks, ingest){
  const points = [
    ...ops.map((e,i) => ({ t:e.t, kind:"ops", ok:e.ok,
      title:"🎛️ "+e.cmd, d:e.d, idx:"ops"+i })),
    ...ticks.map((e,i) => ({ t:e.t, kind:e.kind, ok:e.ok,
      title:(TRIGGER_GLYPH[e.kind]+" ")+(e.mode==="baseline"?"baseline tick":e.mode==="light"?"light tick":"wake"),
      d:e.d, idx:"tick"+i })),
    ...ingest.map((e,i) => ({ t:e.t, kind:"ingest", ok:e.ok,
      title:"📥 "+e.source, d:"→ "+e.target.lane, idx:"ingest"+i })),
  ];
  const groups = {};
  points.forEach(p => { (groups[p.t] = groups[p.t] || []).push(p); });
  return Object.keys(groups).map(t => {
    const events = groups[t].sort((a,b) => TRIGGER_PRIORITY[a.kind] - TRIGGER_PRIORITY[b.kind]);
    return { t, events };
  });
}

const HEALTH_COLOR = { up:"#7CB342", busy:"#f5c344", down:"#e5484d", paused:"#4da3ff" };
const HEALTH_LABEL = { up:"정상 · 트리거 대기", busy:"트리거 처리 중", down:"다운 · 트리거 대기 불가", paused:"일시정지 · 트리거 대기 불가" };
function addMinutes(hhmm, min){ return fmtHM(((minutesOf(hhmm) + min) % 1440 + 1440) % 1440); }
function buildLayeredSegs(layers){
  const points = new Set([0, 1440]);
  layers.forEach(l => l.ranges.forEach(r => { points.add(minutesOf(r.from)); points.add(minutesOf(r.to)); }));
  const sorted = Array.from(points).sort((a,b) => a-b);
  const segs = [];
  for (let i = 0; i < sorted.length - 1; i++) {
    const m0 = sorted[i], m1 = sorted[i+1];
    if (m0 >= m1) continue;
    const mid = (m0 + m1) / 2;
    let state = "up";
    layers.forEach(l => { if (l.ranges.some(r => minutesOf(r.from) <= mid && mid < minutesOf(r.to))) state = l.state; });
    const last = segs[segs.length - 1];
    if (last && last.s === state) last.to = fmtHM(m1);
    else segs.push({ s: state, from: fmtHM(m0), to: fmtHM(m1) });
  }
  return segs;
}
const BACKEND_BUSY_MIN = 2; // 트리거 1건 처리에 걸리는 대략적 시간(분) — 실측 아닌 근사치
function pausedRanges(ops){
  const sorted = ops.filter(e => e.cmd === "/pause" || e.cmd === "/resume").slice()
    .sort((a,b) => minutesOf(a.t) - minutesOf(b.t));
  const ranges = [];
  let openPause = null;
  sorted.forEach(e => {
    if (e.cmd === "/pause") openPause = e.t;
    else if (e.cmd === "/resume" && openPause) { ranges.push({from:openPause, to:e.t}); openPause = null; }
  });
  if (openPause) ranges.push({from:openPause, to:"30:00"});
  return ranges;
}
function computeBackendSegs(ticks, ops, downRanges){
  return buildLayeredSegs([
    { state:"busy",   ranges: ticks.map(e => ({ from:e.t, to:addMinutes(e.t, BACKEND_BUSY_MIN) })) },
    { state:"paused", ranges: pausedRanges(ops) },
    { state:"down",   ranges: downRanges || [] },
  ]);
}

function renderStats(){
  const boolPoint = [...TICKS, ...OPS, ...INGEST];
  const tonePoint = [...RELAY, ...NOTICE, ...TWEET];
  const previewSegs = PREVIEW.flatMap(v => v.segs);
  const errors = boolPoint.filter(e => !e.ok).length + tonePoint.filter(e => e.tone === "err").length;
  const degraded = tonePoint.filter(e => e.tone === "degraded").length + previewSegs.filter(sg => sg.q === "degraded").length;
  const previewFails = previewSegs.filter(sg => sg.q === "err").length;
  const ytUsed = TICKS.reduce((s,e) => s + (e.quota||0), 0);
  const tiles = [
    { v: boolPoint.length + tonePoint.length + previewSegs.length, s: "총 이벤트" },
    { v: errors + previewFails, s: "에러 발생", err: true },
    { v: degraded, s: "부분 실패(degraded)" },
    { v: `${ytUsed} / 10,000`, s: "YouTube quota(기록된 실행)" },
  ];
  document.getElementById("statList").innerHTML = tiles.map(t =>
    `<div class="stat-item${t.err?' error':''}"><b>${t.v}</b><span>${t.s}</span></div>`
  ).join("");

  document.getElementById("memberGrid").innerHTML = ROWS_MEMBERS.map(m => {
    const tw = TWEET.filter(e => e.member === m);
    const ok = tw.filter(e => e.tone !== "err").length;
    const err = tw.filter(e => e.tone === "err").length;
    const live = (PREVIEW.find(v => v.member === m)?.segs || []).some(sg => sg.s === "live");
    const breakdown = tw.length
      ? `<span class="ok">✓${ok}</span>${err ? ` <span class="err">✕${err}</span>` : ""}`
      : "";
    return `<div class="m-row">
      <div class="m-who"><img src="${MEMBER_ICON[m]}" alt="${MEMBER_KO[m]}"><span>${MEMBER_KO[m]}</span></div>
      <div class="m-tweet"><b>${tw.length}건</b>${breakdown}</div>
      <div class="live-dot ${live ? "on" : "off"}" title="${live ? "라이브 감지됨" : "라이브 없음"}"></div>
    </div>`;
  }).join("");

  const noticeOk = NOTICE.filter(e => e.tone !== "err").length;
  const noticeErr = NOTICE.filter(e => e.tone === "err").length;
  document.getElementById("noticeLine").innerHTML = `
    <span class="label">소식 등록</span>
    <span class="figures"><span class="ok"><b>${noticeOk}</b>성공</span><span class="err"><b>${noticeErr}</b>실패</span><span><b>${NOTICE.length}</b>건 총계</span></span>
  `;
}

const activeTones = new Set(["ok","degraded","err"]);
const legendEl = document.getElementById("legend");
[["ok","정상",OK],["degraded","부분 실패",DEGRADED],["err","에러",ERR]].forEach(([key,label,color]) => {
  const btn = document.createElement("button");
  btn.innerHTML = `<i style="background:${color}"></i>${label}`;
  btn.addEventListener("click", () => {
    if (activeTones.has(key)) activeTones.delete(key); else activeTones.add(key);
    if (activeTones.size === 0) ["ok","degraded","err"].forEach(k => activeTones.add(k));
    btn.classList.toggle("off", !activeTones.has(key));
    renderTimeline(); renderTable();
  });
  legendEl.appendChild(btn);
});
function stateChipsHtml(){
  const chips = Object.entries(STATE).map(([k,v]) => {
    const bg = k === "watching"
      ? "repeating-linear-gradient(45deg, #f5c344 0 3px, #9aa0a8 3px 6px)" : v.color;
    return `<span class="lg-chip"><i style="background:${bg}"></i>${v.label}</span>`;
  });
  // (v3.8.4 item 10) live 미만 확신도 추정("assumed_live") — 실제로는 announced/upcoming
  // 상태값 위에 덧씌워지는 표시라 STATE 열거에는 없어 따로 추가.
  chips.push(`<span class="lg-chip"><i style="background:repeating-linear-gradient(45deg, #ff5470 0 3px, #9aa0a8 3px 6px)"></i>방송 중 추정(live·assumed)</span>`);
  return `<div class="lg-chips">` + chips.join("") + `</div>`;
}
function resultChipsHtml(keys){
  return `<div class="lg-chips">` + keys.map(k =>
    `<span class="lg-chip"><i style="background:${TONE_COLOR[k]}"></i>${TONE_LABEL[k]}</span>`
  ).join("") + `</div>`;
}
function toneChipsHtml(){ return resultChipsHtml(["ok","degraded","err"]); }
function laneLegendHtml(key){
  if (key === "trigger") return `<div class="lg-title">🎯 트리거</div>` +
    `<div class="lg-sub">4가지 트리거(🎛️ 운영자 제어·🕒 정기수집·📡 라이브 감지·📥 X 웹훅) 를 짧은 세로` +
    ` 막대 하나로 표시, 막대 색은 결과(하나라도 실패면 빨강). 같은 시각에 여러 건이 뭉치면 막대 높이로` +
    ` 개수를 나타낸다(5건↑는 고정) — 어떤 종류인지·상세 내역은 막대 위 호버/클릭으로.</div>` +
    resultChipsHtml(["ok","err"]) +
    `<div class="lg-chips">` +
      `<span class="lg-chip">🎛️ 운영자 제어</span><span class="lg-chip">🕒 정기수집 tick</span>` +
      `<span class="lg-chip">📡 라이브 감지(wake)</span><span class="lg-chip">📥 X 웹훅 인입</span>` +
    `</div>`;
  if (key === "health") return `<div class="lg-title">🖥️ 백엔드 상태</div>` +
    `<div class="lg-sub">healthchecks.io status/flips + tick·wake·pause 로그로 재구성.</div>` +
    `<div class="lg-chips">` + Object.entries(HEALTH_LABEL).map(([k,label]) =>
      `<span class="lg-chip"><i style="background:${HEALTH_COLOR[k]}"></i>${label}</span>`
    ).join("") + `</div>`;
  if (key === "preview") return `<div class="lg-title">preview 상태</div>` +
    `<div class="lg-sub">굵은 줄 색 = 그 순간 상태(6단계). live 미만은 확신도가 낮을수록 어두운 노랑` +
    `(announced &lt; upcoming = watching, watching은 같은 노랑에 빗금). 아직 미확인인데 방송 중으로` +
    ` 추정되는 구간(assumed_live)은 빨강 빗금으로 덮어 표시.</div>` +
    stateChipsHtml() +
    `<div class="lg-sub" style="margin-top:2px">줄 위 작은 점 = 그 전이 자체의 품질</div>` + toneChipsHtml();
  if (key === "relay") return `<div class="lg-title">X 예고 릴레이</div><div class="lg-sub">공식 계정 게시물 파싱 결과.</div>` + toneChipsHtml();
  if (key === "notice") return `<div class="lg-title">소식</div><div class="lg-sub">공식 계정의 방송 외 이벤트 게시물 처리 결과.</div>` + toneChipsHtml();
  if (key === "tweet") return `<div class="lg-title">개인 트윗</div><div class="lg-sub">멤버 개인 트윗 처리 결과.</div>` + toneChipsHtml();
  return "";
}

const ROWS_MEMBERS = ["arale","yuno","nonoka","ritsu","miyako"];
// 모바일(폭 640px 이하)은 라벨을 아이콘으로 줄여 확보한 공간을 활용해 세로로 좀 더 밀집시킨다.
// (v3.8.4-후속, item 4) 레인 간 간격(GROUP_GAP) 을 조금 넓혀 그룹 아이콘 뱃지(item 3)가 위아래
// 그룹과 시각적으로 안 붙어 보이게 함. trigger 레인은 rowH=110→64 — 점을 짧은 세로 막대로
// 바꾸면서(사용자 제안: 원 면적보다 막대 높이가 개수 비교에 더 정확) 세로 여유가 훨씬 덜
// 필요해짐(막대 최대 높이 48 기준 ±24 로 충분히 안전, ±32 확보).
const IS_NARROW = window.matchMedia("(max-width:640px)").matches;
const ROW_H_POINT = IS_NARROW ? 18 : 24, ROW_H_BAR = IS_NARROW ? 22 : 28, GROUP_GAP = IS_NARROW ? 12 : 20;
const PAD_R = 24, PAD_T = 10, PAD_B = 26;
const BASE_W = 900;
const LANES = [
  // (후속) 막대 최대 높이(호버 확대 포함) 48px — rowH 절반(desktop 32) 안에 여유 있게 들어감.
  { key:"trigger", label:"트리거",      icon:"🎯", type:"point", rows:["all"], rowH: IS_NARROW ? 56 : 64 },
  // (item 2) 백엔드 상태 막대 두께 2배(12→24px) — rowH 도 그만큼 여유 있게 별도 지정
  // (preview 와 같은 ROW_H_BAR 를 공유하지 않게 분리).
  { key:"health",  label:"백엔드 상태", icon:"🖥️", type:"bar",   rows:["backend"], rowH: IS_NARROW ? 32 : 40 },
  { key:"preview", label:"preview",     icon:"🎬", type:"bar",   rows: ROWS_MEMBERS },
  { key:"relay",   label:"X 예고 릴레이", icon:"📣", type:"point", rows:["account"] },
  { key:"notice",  label:"소식",        icon:"📰", type:"point", rows:["notice"] },
  { key:"tweet",   label:"개인 트윗",   icon:"💌", type:"point", rows: ROWS_MEMBERS },
];
const TRIGGER_GLYPH = { ops:"🎛️", tick:"🕒", wake:"📡", ingest:"📥" };

let rowY = {};
(function layout(){
  let y = PAD_T;
  LANES.forEach(g => {
    const rh = g.rowH || (g.type === "bar" ? ROW_H_BAR : ROW_H_POINT);
    const blockTop = y;
    const centerY = y + (g.rows.length * rh) / 2;
    // 그룹 아이콘(왼쪽 28px 칸)과 행 라벨(오른쪽, right-align)을 좌우로 분리해뒀으므로
    // 세로 위치는 그냥 그룹 정중앙이면 된다 — 더 이상 서로 겹칠 일이 없다.
    g._labelY = centerY;
    g.rows.forEach(r => { rowY[g.key+"|"+r] = y + rh/2; y += rh; });
    // (item 3) 그룹의 행 블록 전체 범위 — renderLabels 가 스파인(연결선) 그릴 때 씀.
    g._blockTop = blockTop;
    g._blockHeight = y - blockTop;
    y += GROUP_GAP;
  });
  window._TL_H = y - GROUP_GAP + PAD_B;
})();
// 하루 경계가 00:00 이 아니라 06:00 KST(DAY_START_MIN)이라 — 자정 넘겨 방송하는 멤버가
// 흔해서 방송일 하나를 안 쪼개려는 목적. minutesOf 는 실제 시각을 이 앵커 기준으로
// 회전시켜 0~1439 로 만든다. "30:00" 처럼 24시간을 넘는 표기는 "이 하루의 끝"을 뜻하는
// 가상 시각(파이썬 쪽 now_hm/다운구간 fallback)이라 회전 없이 그대로(1440 근방) 통과시킨다.
const DAY_START_MIN = 60 * 6;
function minutesOf(hhmm){
  const [h,m] = hhmm.split(":").map(Number);
  if (h >= 24) return h*60 + m - DAY_START_MIN;
  return ((h*60+m) - DAY_START_MIN + 1440) % 1440;
}
// 06:00(하루 시작) 라인이 컨테이너 왼쪽 가장자리에 딱 붙어 잘려 보이는 문제 — 왼쪽에
// 실데이터 없는 여유 공백(05:30~06:00) 30분을 얹어 플롯 범위를 넓힌다.
const AXIS_LEAD_MIN = 30;
const AXIS_TOTAL_MIN = 1440 + AXIS_LEAD_MIN;
function minutesToX(min, plotW){ return ((min + AXIS_LEAD_MIN) / AXIS_TOTAL_MIN) * plotW; }
function timeToX(hhmm, plotW){ return minutesToX(minutesOf(hhmm), plotW); }
function xToMinutes(x, plotW){ return (x / plotW) * AXIS_TOTAL_MIN - AXIS_LEAD_MIN; }
const NICE_STEPS_MIN = [1,2,5,10,15,30,60,120,180,240,360,720,1440];
const MIN_TICK_PX = 56;
function pickHourStepMin(plotW){
  const pxPerMin = plotW / AXIS_TOTAL_MIN;
  for (const step of NICE_STEPS_MIN) if (step * pxPerMin >= MIN_TICK_PX) return step;
  return 1440;
}
function fmtHM(min){
  const real = ((min + DAY_START_MIN) % 1440 + 1440) % 1440;
  const h = Math.floor(real/60), m = real % 60;
  return String(h).padStart(2,"0") + ":" + String(m).padStart(2,"0");
}

function renderLabels(){
  const wrap = document.getElementById("tlLabels");
  wrap.style.height = window._TL_H + "px";
  wrap.innerHTML = "";
  LANES.forEach(g => {
    const hasSubRows = g.rows.some(r => MEMBER_KO[r]);
    // (item 3) 하위 멤버 뱃지가 있는 그룹(preview·tweet)만 세로 스파인을 그려 "이 그룹 아이콘에
    // 딸린 행들" 임을 보여준다. 그룹 아이콘 뱃지 중심부터 마지막 행까지 관통.
    if (hasSubRows) {
      const spine = document.createElement("div");
      spine.className = "grp-spine";
      spine.style.top = g._blockTop + "px";
      spine.style.height = g._blockHeight + "px";
      wrap.appendChild(spine);
    }
    const grp = document.createElement("div");
    grp.className = "grp"; grp.style.top = g._labelY + "px"; grp.textContent = g.icon; grp.title = g.label;
    wireLegend(grp, () => laneLegendHtml(g.key));
    wrap.appendChild(grp);
    g.rows.forEach(r => {
      if (!MEMBER_KO[r]) return;
      const row = document.createElement("div");
      row.className = "row"; row.style.top = rowY[g.key+"|"+r] + "px"; row.title = MEMBER_KO[r];
      const img = document.createElement("img");
      img.src = MEMBER_ICON[r]; img.alt = MEMBER_KO[r]; img.width = 16; img.height = 16;
      row.appendChild(img);
      wrap.appendChild(row);
    });
  });
}

const ZOOM_LEVELS = [1, 1.5, 2, 3, 4, 6, 8];
let zoomIdx = 0;
let triggerMarks = [];
let crosshairMinutes = null; // 크로스헤어가 가리키는 "시각"(분) — 줌해도 화면상 같은 시각에 고정하는 기준
function currentPlotW(){ return BASE_W * ZOOM_LEVELS[zoomIdx]; }
function viewportCenterMinutes(){
  const scrollEl = document.getElementById("tlScroll");
  return xToMinutes(scrollEl.scrollLeft + scrollEl.clientWidth / 2, currentPlotW());
}
// anchorMinutes 를 화면상 같은 위치에 고정한 채 줌 레벨만 바꾼다. 버튼 클릭은 크로스헤어가
// 있으면 그 시각, 없으면 뷰포트 중앙을 기준으로 삼는다(휠·핀치는 호출부에서 직접 넘김).
function setZoom(idx, anchorMinutes){
  const newIdx = Math.max(0, Math.min(ZOOM_LEVELS.length - 1, idx));
  if (newIdx === zoomIdx) return;
  const scrollEl = document.getElementById("tlScroll");
  const anchorMin = anchorMinutes != null ? anchorMinutes : viewportCenterMinutes();
  const oldPlotW = currentPlotW();
  const offsetInView = minutesToX(anchorMin, oldPlotW) - scrollEl.scrollLeft;
  zoomIdx = newIdx;
  document.getElementById("zoomLabel").textContent = Math.round(ZOOM_LEVELS[zoomIdx]*100) + "%";
  renderTimeline();
  const newPlotW = currentPlotW();
  scrollEl.scrollLeft = Math.max(0, minutesToX(anchorMin, newPlotW) - offsetInView);
  if (crosshairMinutes != null) placeCrosshair(crosshairMinutes);
}
document.getElementById("zoomIn").addEventListener("click", () => { if (!isPinned()) setZoom(zoomIdx+1, crosshairMinutes); });
document.getElementById("zoomOut").addEventListener("click", () => { if (!isPinned()) setZoom(zoomIdx-1, crosshairMinutes); });
document.getElementById("zoomReset").addEventListener("click", () => { if (!isPinned()) setZoom(0, crosshairMinutes); });

function renderTimeline(){
  const svg = document.getElementById("tlSvg");
  const plotW = BASE_W * ZOOM_LEVELS[zoomIdx], H = window._TL_H;
  const totalW = plotW + PAD_R;
  svg.setAttribute("viewBox", `0 0 ${totalW} ${H}`);
  svg.removeAttribute("preserveAspectRatio");
  svg.setAttribute("width", totalW);
  svg.setAttribute("height", H);
  svg.style.width = totalW + "px";
  svg.style.height = H + "px";
  const ns = "http://www.w3.org/2000/svg";
  svg.innerHTML = "";
  triggerMarks = [];

  const defs = document.createElementNS(ns, "defs");
  // (v3.8.4 item 10) 패턴 2종 — 둘 다 같은 모양(6x6, 45도, 절반 줄무늬), 바탕색만 다르다.
  // watchHatch = watching(노랑 바탕), liveAssumedHatch = assumed_live 덮어쓰기(빨강 바탕).
  function makeHatch(id, bg){
    const hatch = document.createElementNS(ns, "pattern");
    hatch.setAttribute("id", id);
    hatch.setAttribute("width", "6"); hatch.setAttribute("height", "6");
    hatch.setAttribute("patternTransform", "rotate(45)");
    hatch.setAttribute("patternUnits", "userSpaceOnUse");
    const hatchBg = document.createElementNS(ns, "rect");
    hatchBg.setAttribute("width", "6"); hatchBg.setAttribute("height", "6"); hatchBg.setAttribute("fill", bg);
    hatch.appendChild(hatchBg);
    const hatchStripe = document.createElementNS(ns, "rect");
    hatchStripe.setAttribute("width", "3"); hatchStripe.setAttribute("height", "6"); hatchStripe.setAttribute("fill", "#9aa0a8");
    hatch.appendChild(hatchStripe);
    return hatch;
  }
  defs.appendChild(makeHatch("watchHatch", "#f5c344"));
  defs.appendChild(makeHatch("liveAssumedHatch", "#ff5470"));
  svg.appendChild(defs);

  LANES.forEach(g => {
    g.rows.forEach(r => {
      const ry = rowY[g.key+"|"+r];
      const line = document.createElementNS(ns,"line");
      line.setAttribute("x1", 0); line.setAttribute("x2", plotW);
      line.setAttribute("y1", ry); line.setAttribute("y2", ry);
      line.setAttribute("class","tl-lane");
      svg.appendChild(line);
    });
  });

  const stepMin = pickHourStepMin(plotW);
  for (let m = 0; m <= 1440; m += stepMin) {
    const x = minutesToX(m, plotW);
    const tick = document.createElementNS(ns,"line");
    tick.setAttribute("x1", x); tick.setAttribute("x2", x);
    tick.setAttribute("y1", PAD_T - 2); tick.setAttribute("y2", H - PAD_B + 2);
    tick.setAttribute("class","tl-hour");
    svg.appendChild(tick);
    const lbl = document.createElementNS(ns,"text");
    lbl.setAttribute("x", x); lbl.setAttribute("y", H - 8);
    lbl.setAttribute("text-anchor","middle"); lbl.setAttribute("class","tl-hour-label");
    lbl.textContent = fmtHM(m);
    svg.appendChild(lbl);
  }

  (function drawHealthBar(){
    const ry = rowY["health|backend"];
    BACKEND_SEGS.forEach(sg => {
      const x1 = timeToX(sg.from, plotW), x2 = timeToX(sg.to, plotW);
      const rect = document.createElementNS(ns,"rect");
      // (v3.8.4-후속) 세로 두께 2배(12→24) — HEALTH 레인(health|backend)도 rowH 를 따로
      // 키워뒀다(LANES 정의) 그 안에서만 커지므로 다른 레인 침범 없음.
      rect.setAttribute("x", x1); rect.setAttribute("y", ry - 12);
      rect.setAttribute("width", Math.max(x2-x1, 1)); rect.setAttribute("height", 24);
      rect.setAttribute("rx", 5);
      rect.setAttribute("fill", HEALTH_COLOR[sg.s]);
      rect.setAttribute("class","tl-seg");
      wireTip(rect, { t:sg.from+"–"+sg.to, title:HEALTH_LABEL[sg.s], raw:sg.s, tone:sg.s==="down"?"err":"ok", d:"healthchecks.io status/flips 기준" });
      svg.appendChild(rect);
    });
  })();

  PREVIEW.forEach(v => {
    const ry = rowY["preview|"+v.member];
    v.segs.forEach((sg, i) => {
      const x1 = timeToX(sg.from, plotW), x2 = timeToX(sg.to, plotW);
      const rect = document.createElementNS(ns,"rect");
      rect.setAttribute("x", x1); rect.setAttribute("y", ry - 6);
      rect.setAttribute("width", Math.max(x2-x1, 1)); rect.setAttribute("height", 12);
      rect.setAttribute("rx", 3);
      // (v3.8.4 item 10) assumed_live 는 상태(announced/upcoming)와 별개의 "확신도 낮음" 덮어쓰기 —
      // 어떤 상태든 빨강 빗금이 상태색보다 우선.
      const fill = sg.assumed_live ? "url(#liveAssumedHatch)"
                 : sg.s === "watching" ? "url(#watchHatch)"
                 : (STATE_HEX[sg.s] || "#888");
      rect.setAttribute("fill", fill);
      rect.setAttribute("class","tl-seg");
      const q = sg.q || "ok";
      const label = stateLabel(sg.s) + (sg.assumed_live ? " · 추정" : "");
      wireTip(rect, { t:sg.from+"–"+sg.to, title:v.title, raw:label, tone:"ok", d:sg.qd || ("video: "+(v.title||"—")) });
      svg.appendChild(rect);
      if (!(i === 0 && sg.from === "06:00")) {
        const dot = document.createElementNS(ns,"circle");
        dot.setAttribute("cx", x1); dot.setAttribute("cy", ry);
        dot.setAttribute("r", 3); dot.setAttribute("fill", TONE_COLOR[q]);
        dot.setAttribute("class", "tl-dot" + (activeTones.has(q) ? "" : " dim"));
        wireTip(dot, { t:sg.from, title:v.title, raw:label+" 전이 · "+TONE_LABEL[q], tone:q, d:sg.qd || "" });
        svg.appendChild(dot);
      }
    });
  });

  function drawDot(t, ry, tone, tipData){
    const x = timeToX(t, plotW);
    const el = document.createElementNS(ns,"circle");
    el.setAttribute("cx", x); el.setAttribute("cy", ry); el.setAttribute("r", 5);
    el.setAttribute("fill", TONE_COLOR[tone]);
    el.setAttribute("class", "tl-dot" + (activeTones.has(tone) ? "" : " dim"));
    wireTip(el, tipData);
    svg.appendChild(el);
  }
  // (v3.8.4 item 8) 같은 시각의 트리거 이벤트 그룹 하나 = 점 하나. 대표 아이콘은
  // TRIGGER_PRIORITY 순 맨 앞(ops>ingest>tick/wake), 반지름은 개수로, 색은 그룹 안에
  // 실패가 하나라도 있으면 err. 상세 목록은 호버/클릭(wireLegend, 기존 범례와 같은
  // pin-on-click 메커니즘 재사용)으로.
  function triggerGroupDetailHtml(t, events){
    const rows = events.map(e =>
      `<div class="lg-chip"><i style="background:${e.ok?OK:ERR}"></i>${e.title}</div>` +
      (e.d ? `<div class="lg-note" style="border-top:none;padding-top:0;margin:-2px 0 6px 16px">${e.d}</div>` : "")
    ).join("");
    return `<div class="lg-title">${t} · 트리거 ${events.length}건</div>` + rows;
  }
  // (v3.8.4-후속) 점 위 아이콘 글리프 제거 — 호버/클릭 팝업(triggerGroupDetailHtml)에 종류별
  // 아이콘·이름·결과가 전부 뜨므로 점 위에 또 아이콘을 얹을 필요가 없다. 순수하게 점 하나 +
  // 크기(개수)·색(결과)만으로 표시.
  function drawTriggerGroup(t, events){
    const x = timeToX(t, plotW);
    const cy = rowY["trigger|all"];
    const count = events.length;
    const hBase = triggerBarHeightBase(count), hActive = triggerBarHeightActive(count);
    const anyErr = events.some(e => !e.ok);
    const dimmed = !activeTones.has(anyErr ? "err" : "ok");
    const bar = document.createElementNS(ns,"rect");
    bar.setAttribute("x", x - TRIGGER_BAR_W/2); bar.setAttribute("y", cy - hBase/2);
    bar.setAttribute("width", TRIGGER_BAR_W); bar.setAttribute("height", hBase);
    bar.setAttribute("rx", 2);
    bar.setAttribute("fill", anyErr ? ERR : OK);
    bar.setAttribute("class", "tl-trigger-bar" + (dimmed ? " dim" : ""));
    svg.appendChild(bar);
    wireLegend(bar, () => triggerGroupDetailHtml(t, events));
    triggerMarks.push({ x, cy, bar, hBase, hActive });
  }

  TRIGGER_GROUPS.forEach(g => drawTriggerGroup(g.t, g.events));
  RELAY.forEach((e, i) => drawDot(e.t, rowY["relay|account"], e.tone,
    { t:e.t, title:"BDP_yumemita", raw:TONE_LABEL[e.tone], tone:e.tone, d:e.d, _idx:"relay"+i }));
  NOTICE.forEach((e, i) => drawDot(e.t, rowY["notice|notice"], e.tone,
    { t:e.t, title:"소식", raw:TONE_LABEL[e.tone], tone:e.tone, d:e.d, _idx:"notice"+i }));
  TWEET.forEach((e, i) => drawDot(e.t, rowY["tweet|"+e.member], e.tone,
    { t:e.t, title:(MEMBER_KO[e.member]||e.member)+" 개인 트윗", raw:TONE_LABEL[e.tone], tone:e.tone, d:e.d, _idx:"tweet"+i }));

  document.getElementById("tlSub").textContent =
    "점/막대 위에 마우스를 올리면 시간·제목·결과가 보이고, 클릭하면 상세(트리거는 목록, 그 외는 아래 표의 해당 행)가 열립니다.";
}

const STATE_HEX = { announced:"#8a6d1a", upcoming:"#f5c344", watching:"#f5c344", live:"#ff5470", end:"#575757", none:"#424242" };

function showTip(ev, data){
  const tt = document.getElementById("tooltip");
  tt.innerHTML = `<div class="tt-h">${data.t}</div>` +
    (data.title ? `<div class="tt-title">${data.title}</div>` : "") +
    `<div class="tt-raw ${data.tone}">${data.raw}</div>` +
    (data.d ? `<div class="tt-d">${data.d}</div>` : "");
  tt.style.display = "block";
  tt.style.left = (ev.clientX + 14) + "px";
  tt.style.top = (ev.clientY + 14) + "px";
}
function hideTip(){ document.getElementById("tooltip").style.display = "none"; }
function jumpToRow(idx){
  const row = document.querySelector(`#evBody tr[data-idx="${idx}"]`);
  if (!row) return;
  row.scrollIntoView({ behavior:"smooth", block:"center" });
  row.classList.remove("flash"); void row.offsetWidth; row.classList.add("flash");
}

let pinned = false;
function isPinned(){ return pinned; }
function pinTip(ev, tipData){
  if (pinned) return;
  pinned = true;
  showTip(ev, tipData);
  document.getElementById("tlScroll").classList.add("locked");
}
function unpinTip(){
  if (!pinned) return;
  pinned = false;
  hideTip();
  document.getElementById("tlScroll").classList.remove("locked");
}
function wireTip(el, tipData){
  el.addEventListener("mousemove", (ev) => { if (!isPinned()) showTip(ev, tipData); });
  el.addEventListener("mouseleave", () => { if (!isPinned()) hideTip(); });
  el.addEventListener("click", (ev) => {
    ev.stopPropagation();
    if (isPinned()) return;
    pinTip(ev, tipData);
    if (tipData._idx) jumpToRow(tipData._idx);
  });
}
document.addEventListener("click", (ev) => {
  if (!pinned) return;
  if (document.getElementById("tooltip").contains(ev.target)) return;
  if (document.getElementById("tlScroll").contains(ev.target)) return; // 그 안의 클릭은 자체 토글 핸들러가 처리
  unpinTip();
});
function showLegendHtml(ev, html){
  const tt = document.getElementById("tooltip");
  tt.innerHTML = html;
  tt.style.display = "block";
  tt.style.left = (ev.clientX + 14) + "px";
  tt.style.top = (ev.clientY + 14) + "px";
}
function wireLegend(el, htmlFn){
  el.addEventListener("mousemove", (ev) => { if (!isPinned()) showLegendHtml(ev, htmlFn()); });
  el.addEventListener("mouseleave", () => { if (!isPinned()) hideTip(); });
  el.addEventListener("click", (ev) => {
    ev.stopPropagation();
    if (isPinned()) return;
    pinned = true;
    showLegendHtml(ev, htmlFn());
    document.getElementById("tlScroll").classList.add("locked");
  });
}

const TRIGGER_HOVER_SNAP_PX = 40;
function setTriggerActiveNear(x){
  if (!triggerMarks.length) return;
  let bestX = null, bestDist = Infinity;
  if (x != null) triggerMarks.forEach(m => { const d = Math.abs(m.x - x); if (d < bestDist) { bestDist = d; bestX = m.x; } });
  const snap = x != null && bestDist <= TRIGGER_HOVER_SNAP_PX;
  triggerMarks.forEach(m => {
    const active = snap && m.x === bestX;
    // (후속) 점 → 막대로 바뀌면서 반지름 대신 높이(그리고 그에 맞춘 y)를 조정한다.
    // 중심(cy)을 기준으로 위아래 대칭 확장 — 다른 값은 그대로 두고 크기만 커 보이게.
    const h = active ? m.hActive : m.hBase;
    m.bar.setAttribute("height", h);
    m.bar.setAttribute("y", m.cy - h/2);
  });
}

function buildRows(){
  const rows = [];
  OPS.forEach((e,i) => rows.push({ t:e.t, lane:"운영자 제어", who:e.cmd, raw:e.ok?"ok":"error", d:e.d, tone:e.ok?"ok":"err", idx:"ops"+i }));
  TICKS.forEach((e,i) => rows.push({ t:e.t, lane:"정기수집·라이브감지", who:e.mode, raw:e.ok?"ok":"error", d:e.d, tone:e.ok?"ok":"err", idx:"tick"+i }));
  INGEST.forEach((e,i) => rows.push({ t:e.t, lane:"X 웹훅 인입", who:e.source, raw:e.ok?"ok":"error", d:"→ "+e.target.lane, tone:e.ok?"ok":"err", idx:"ingest"+i }));
  RELAY.forEach((e,i) => rows.push({ t:e.t, lane:"X 예고 릴레이", who:"BDP_yumemita", raw:TONE_LABEL[e.tone], d:e.d, tone:e.tone, idx:"relay"+i }));
  NOTICE.forEach((e,i) => rows.push({ t:e.t, lane:"소식", who:"", raw:TONE_LABEL[e.tone], d:e.d, tone:e.tone, idx:"notice"+i }));
  TWEET.forEach((e,i) => rows.push({ t:e.t, lane:"개인 트윗", who:MEMBER_KO[e.member]||e.member, raw:TONE_LABEL[e.tone], d:e.d, tone:e.tone, idx:"tweet"+i }));
  PREVIEW.forEach(v => {
    v.segs.forEach((sg,i) => {
      const skip = i === 0 && sg.from === "06:00";
      rows.push({ t:sg.from, lane:"preview", who:(MEMBER_KO[v.member]||v.member)+(v.title?" · "+v.title:""),
        raw:(STATE[sg.s]||{label:sg.s}).label + (skip ? "" : " · "+TONE_LABEL[sg.q||"ok"]), d:sg.qd||"", tone:skip?"ok":(sg.q||"ok"), idx:null, isState:true });
    });
  });
  BACKEND_SEGS.forEach(sg => rows.push({ t:sg.from, lane:"백엔드 상태", who:"backend", raw:HEALTH_LABEL[sg.s], d:"", tone:"ok", idx:null, isState:true }));
  rows.sort((a,b) => minutesOf(a.t) - minutesOf(b.t));
  return rows;
}
function renderTable(){
  const rows = buildRows();
  document.getElementById("evBody").innerHTML = rows.map(r => {
    const hidden = r.isState || activeTones.has(r.tone) ? "" : "filtered";
    const color = r.isState ? "#8a8f98" : TONE_COLOR[r.tone];
    return `<tr data-idx="${r.idx}" class="${hidden}">` +
      `<td class="t-time">${r.t}</td><td>${r.lane}</td><td class="t-who">${r.who || "—"}</td>` +
      `<td class="t-raw"><span class="dot-swatch" style="background:${color}"></span>${r.raw}</td>` +
      `<td class="t-detail">${r.d || "—"}</td></tr>`;
  }).join("");
}

function grassTone(dateStr){
  const day = REPORT.days[dateStr];
  if (!day) return null; // 아직 안 온 날짜(이번 달의 남은 날) — 데이터 없음
  const previewSegs = day.preview.flatMap(v => v.segs);
  const hasErr = day.ticks.some(e => !e.ok) || day.ops.some(e => !e.ok) ||
    day.relay.some(e => e.tone === "err") || day.notice.some(e => e.tone === "err") ||
    day.tweet.some(e => e.tone === "err") || previewSegs.some(sg => sg.q === "err");
  if (hasErr) return "err";
  const hasDeg = day.relay.some(e => e.tone === "degraded") || day.notice.some(e => e.tone === "degraded") ||
    day.tweet.some(e => e.tone === "degraded") || previewSegs.some(sg => sg.q === "degraded");
  if (hasDeg) return "degraded";
  return day.eventCount > 0 ? "ok" : "none";
}
const GRASS_COLOR = { ok:OK, degraded:DEGRADED, err:ERR, none:"#21232a" };
function renderGrass(){
  const panel = document.getElementById("grassPanel");
  if (!REPORT.full || REPORT.month.length <= 1) { panel.hidden = true; return; }
  panel.hidden = false;
  const wrap = document.getElementById("grass");
  wrap.innerHTML = "";
  REPORT.month.forEach(d => {
    const tone = grassTone(d);
    const btn = document.createElement("button");
    const known = tone !== null;
    btn.textContent = String(parseInt(d.slice(8,10), 10));
    btn.style.background = known ? GRASS_COLOR[tone] : GRASS_COLOR.none;
    btn.style.color = known && tone !== "none" ? "#0d0e12" : "var(--muted-2)";
    btn.title = d + (known ? ` · 이벤트 ${REPORT.days[d].eventCount}건` : " · 데이터 없음");
    btn.classList.toggle("sel", d === currentDate);
    if (!known) { btn.classList.add("future"); }
    else btn.addEventListener("click", () => loadDay(d));
    wrap.appendChild(btn);
  });
}

let currentDate = null;
function loadDay(dateStr){
  const day = REPORT.days[dateStr];
  if (!day) return;
  currentDate = dateStr;
  CURRENT_DAY = day;
  PREVIEW = day.preview; TICKS = day.ticks; OPS = day.ops;
  NOTICE = day.notice; TWEET = day.tweet; RELAY = day.relay;
  INGEST = computeIngest(RELAY, NOTICE, TWEET);
  TRIGGER_GROUPS = groupTriggerEvents(OPS, TICKS, INGEST);
  BACKEND_SEGS = computeBackendSegs(TICKS, OPS, day.downRanges);

  document.getElementById("lede").innerHTML =
    `<b>${dateStr}</b> 하루치(06:00~익일 06:00 KST 기준) — 운영자 제어·정기수집 틱·X 웹훅 인입(트리거) → ` +
    `preview·릴레이·소식·개인 트윗(결과)을 같은 시간축에서 대조합니다. ` +
    (REPORT.full ? "위 월간 그리드에서 다른 날짜를 고를 수 있습니다." : `다른 날짜는 <code>/monitor YYYY-MM-DD</code>, 이번 달 전체는 <code>/monitor --full</code>로 요청하세요.`);
  document.getElementById("tlTitle").textContent = dateStr + " · 24시간 타임라인 (06:00~익일 06:00 KST)";
  renderStats();
  renderTimeline();
  renderTable();
  renderExtYoutube();
  renderExtVercel();
  document.getElementById("footer").textContent =
    `생성 기준: ${dateStr}(06:00~익일 06:00 KST) · 총 ${day.eventCount || 0}건 기록 · Ops Monitor(구 Push Monitor)`;
  renderGrass();
}
renderLabels();
loadDay(REPORT.date);

// ── 타임라인 인터랙션 (PC/모바일 공통, Pointer Events) ──────────────────────────
// PC(모바일): 드래그(pan)=좌우 이동 · ctrl+휠(pinch)=현재 크로스헤어 기준 확대/축소 ·
// 클릭(터치)=크로스헤어 고정/풀기.
function clientXToMinutes(clientX){
  const scrollEl = document.getElementById("tlScroll");
  const rect = scrollEl.getBoundingClientRect();
  return xToMinutes(clientX - rect.left + scrollEl.scrollLeft, currentPlotW());
}
function placeCrosshair(minutes){
  crosshairMinutes = minutes;
  const crosshair = document.getElementById("tlCrosshair");
  crosshair.style.left = minutesToX(minutes, currentPlotW()) + "px";
  crosshair.style.height = (document.getElementById("tlSvg").getAttribute("height") || 0) + "px";
  crosshair.style.display = "block";
  setTriggerActiveNear(minutesToX(minutes, currentPlotW()));
}
function hideCrosshair(){
  document.getElementById("tlCrosshair").style.display = "none";
  crosshairMinutes = null;
  setTriggerActiveNear(null);
}

(function setupInteraction(){
  const scrollEl = document.getElementById("tlScroll");
  const pointers = new Map(); // pointerId → clientX (핀치 거리 계산용)
  let dragging = false, dragMoved = false, dragStartX = 0, dragStartScroll = 0;
  let pinchStartDist = null, pinchStartZoomIdx = 0, pinchAnchorMin = null;
  const DRAG_THRESHOLD = 4; // 이 이상 움직이면 드래그로 간주 — 뒤이은 click(탭)의 고정 토글을 막음

  function pinchDist(){
    const xs = [...pointers.values()];
    return Math.abs(xs[0] - xs[1]);
  }

  scrollEl.addEventListener("pointerdown", (ev) => {
    pointers.set(ev.pointerId, ev.clientX);
    scrollEl.setPointerCapture(ev.pointerId);
    if (pointers.size === 2) {
      dragging = false;
      scrollEl.classList.remove("dragging");
      pinchStartDist = pinchDist();
      pinchStartZoomIdx = zoomIdx;
      const [x1, x2] = [...pointers.values()];
      pinchAnchorMin = crosshairMinutes != null ? crosshairMinutes : clientXToMinutes((x1 + x2) / 2);
    } else if (pointers.size === 1 && !isPinned()) {
      dragging = true; dragMoved = false;
      dragStartX = ev.clientX; dragStartScroll = scrollEl.scrollLeft;
      scrollEl.classList.add("dragging");
    }
  });

  scrollEl.addEventListener("pointermove", (ev) => {
    if (!pointers.has(ev.pointerId)) {
      // 버튼 안 누른 호버 — 크로스헤어 미리보기만(고정 중엔 건드리지 않음)
      if (!isPinned() && pointers.size === 0) placeCrosshair(clientXToMinutes(ev.clientX));
      return;
    }
    pointers.set(ev.pointerId, ev.clientX);
    if (pointers.size === 2 && pinchStartDist) {
      const scale = pinchDist() / Math.max(1, pinchStartDist);
      const targetZoom = ZOOM_LEVELS[pinchStartZoomIdx] * scale;
      let bi = 0, bd = Infinity;
      ZOOM_LEVELS.forEach((z, i) => { const d = Math.abs(z - targetZoom); if (d < bd) { bd = d; bi = i; } });
      if (bi !== zoomIdx) setZoom(bi, pinchAnchorMin);
      return;
    }
    if (dragging) {
      const dx = ev.clientX - dragStartX;
      if (Math.abs(dx) > DRAG_THRESHOLD) dragMoved = true;
      scrollEl.scrollLeft = dragStartScroll - dx;
      if (!isPinned()) placeCrosshair(clientXToMinutes(ev.clientX));
    }
  });

  function endPointer(ev){
    pointers.delete(ev.pointerId);
    try { scrollEl.releasePointerCapture(ev.pointerId); } catch (e) {}
    if (pointers.size < 2) pinchStartDist = null;
    if (pointers.size === 0) { dragging = false; scrollEl.classList.remove("dragging"); }
  }
  scrollEl.addEventListener("pointerup", endPointer);
  scrollEl.addEventListener("pointercancel", endPointer);

  scrollEl.addEventListener("mouseleave", () => { if (!isPinned() && pointers.size === 0) hideCrosshair(); });

  scrollEl.addEventListener("click", (ev) => {
    if (dragMoved) { dragMoved = false; return; } // 드래그 끝의 관성 클릭 무시
    if (isPinned()) { unpinTip(); return; }
    placeCrosshair(clientXToMinutes(ev.clientX));
    pinned = true;
    scrollEl.classList.add("locked");
  });

  // ctrl+휠(macOS 트랙패드 핀치도 브라우저가 ctrlKey:true 휠 이벤트로 보냄) = 현재
  // 크로스헤어 기준 확대/축소. ctrl 없는 일반 휠은 가로채지 않고 브라우저 기본 동작에 맡긴다.
  scrollEl.addEventListener("wheel", (ev) => {
    if (!ev.ctrlKey) return;
    ev.preventDefault();
    if (isPinned()) return;
    const anchor = crosshairMinutes != null ? crosshairMinutes : clientXToMinutes(ev.clientX);
    setZoom(zoomIdx + (ev.deltaY < 0 ? 1 : -1), anchor);
  }, { passive:false });
})();

function switchTab(which){
  document.getElementById("tabApp").hidden = which !== "app";
  document.getElementById("tabExt").hidden = which !== "ext";
  document.getElementById("tabBtnApp").classList.toggle("active", which === "app");
  document.getElementById("tabBtnExt").classList.toggle("active", which === "ext");
  document.getElementById("tabBtnApp").setAttribute("aria-selected", which === "app");
  document.getElementById("tabBtnExt").setAttribute("aria-selected", which === "ext");
}
document.getElementById("tabBtnApp").addEventListener("click", () => switchTab("app"));
document.getElementById("tabBtnExt").addEventListener("click", () => switchTab("ext"));

function renderExtYoutube(){
  const ytUsed = TICKS.reduce((s,e) => s + (e.quota||0), 0);
  document.getElementById("extYtUsed").textContent = ytUsed.toLocaleString();
  document.getElementById("extYtCalls").textContent = TICKS.length;
  const svg = document.getElementById("extYtChart");
  const ns = "http://www.w3.org/2000/svg";
  const W = 900, H = 120, PADL = 40, PADB = 20, PADT = 10;
  const pw = W - PADL - 10, ph = H - PADT - PADB;
  const sorted = TICKS.slice().sort((a,b) => minutesOf(a.t) - minutesOf(b.t));
  let cum = 0;
  const pts = [[0,0]];
  sorted.forEach(e => { cum += e.quota||0; pts.push([minutesOf(e.t), cum]); });
  pts.push([1440, cum]);
  const maxY = Math.max(1, cum);
  const px = m => PADL + (m/1440)*pw, py = v => PADT + ph - (v/maxY)*ph;
  svg.innerHTML = "";
  const path = document.createElementNS(ns,"path");
  path.setAttribute("d", pts.map(([m,v],i) => (i===0?"M":"L")+px(m)+","+py(v)).join(" "));
  path.setAttribute("fill","none"); path.setAttribute("stroke","#4da3ff"); path.setAttribute("stroke-width","2");
  svg.appendChild(path);
  const cap = document.createElementNS(ns,"text");
  cap.setAttribute("x", PADL); cap.setAttribute("y", PADT+4);
  cap.setAttribute("fill","#8a8f98"); cap.setAttribute("font-size","10");
  cap.textContent = `누적 ${cum} units (${currentDate})`;
  svg.appendChild(cap);
  [0,360,720,1080,1440].forEach(m => {
    const t = document.createElementNS(ns,"text");
    t.setAttribute("x", px(m)); t.setAttribute("y", H-4);
    t.setAttribute("fill","#5f6570"); t.setAttribute("font-size","10");
    t.setAttribute("text-anchor", m===0?"start":m===1440?"end":"middle");
    t.textContent = fmtHM(m);
    svg.appendChild(t);
  });
}

function renderExtVercel(){
  const push = CURRENT_DAY.vercelPush || 0;
  const overLimit = push > 100;
  document.getElementById("extVercelUsed").textContent = push + " / 100";
  document.getElementById("extVercelStatus").textContent = overLimit ? "한도 초과 위험" : "정상";
  document.getElementById("extVercelTile").classList.toggle("error", overLimit);
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    # ── parse_events / _group ──
    text = (
        '{"ts":"2026-09-15T21:02:00Z","flow":"tick","result":"ok","who":"","detail":"d","mode":"baseline","quota":14}\n'
        "garbled line not json\n"
        '{"ts":"2026-09-15T22:15:00Z","flow":"wake","result":"err","who":"v1","detail":"enqueue fail"}\n'
        '{"ts":"2026-09-15T23:00:00Z","flow":"ops","result":"ok","who":"/pause","detail":"control.json 커밋"}\n'
        '{"ts":"2026-09-15T23:30:00Z","flow":"ops","result":"ok","who":"/resume","detail":"재개"}\n'
        '{"ts":"2026-09-15T21:10:00Z","flow":"notice","result":"degraded","who":"","detail":"mode: added, needs_tl=true"}\n'
        '{"ts":"2026-09-15T21:20:00Z","flow":"relay","result":"ok","who":"","detail":"mode: added"}\n'
        '{"ts":"2026-09-15T21:30:00Z","flow":"tweet","result":"ok","who":"arale","detail":"mode: added"}\n'
        '{"ts":"2026-09-15T09:00:00Z","flow":"preview","result":"ok","who":"arale","detail":"upcoming→watching",'
        '"from_state":"upcoming","to_state":"watching","title":"통상방송","assumed_live":true}\n'
    )
    events = parse_events(text)
    assert len(events) == 8, len(events)  # 손상된 줄 1개 제외
    grouped = _group(events)
    assert len(grouped["tick"]) == 2 and len(grouped["ops"]) == 2
    print("[OK] parse_events: 손상된 줄 건너뜀 / _group: tick+wake 합산")

    ticks = _ticks_json(grouped["tick"])
    assert ticks[0]["t"] == "06:02" and ticks[0]["kind"] == "tick" and ticks[0]["quota"] == 14
    assert ticks[1]["kind"] == "wake" and ticks[1]["ok"] is False
    print("[OK] _ticks_json: KST 변환 · tick/wake 구분 · ok=result!=err")

    ops = _ops_json(grouped["ops"])
    assert ops[0]["cmd"] == "/pause" and ops[1]["cmd"] == "/resume"
    print("[OK] _ops_json")

    notice = _tone_json(grouped["notice"])
    assert notice[0]["tone"] == "degraded"
    print("[OK] _tone_json")

    # ── _preview_json: from_state 있는 첫 이벤트 → 선행 세그먼트("06:00"=하루 시작), 없으면 생략 ──
    preview = _preview_json(grouped["preview"], now_hm="12:00")
    arale = next(v for v in preview if v["member"] == "arale")
    assert arale["segs"][0]["s"] == "upcoming" and arale["segs"][0]["from"] == "06:00", arale
    assert arale["segs"][1]["s"] == "watching" and arale["segs"][1]["to"] == "12:00", arale
    ritsu = next(v for v in preview if v["member"] == "ritsu")
    assert ritsu["segs"] == [], "이벤트 없는 멤버는 빈 세그먼트"
    print("[OK] _preview_json: 선행 세그먼트(from_state, 06:00 시작) + 마지막 세그먼트는 now_hm까지")

    # (v3.8.4 item 10) assumed_live 가 이벤트에 있으면 세그먼트에도 실려야 프론트가 빨강
    # 빗금으로 덮어 그릴 수 있다. 선행 세그먼트(근거 이벤트 없음)는 대상 아님.
    assert arale["segs"][1].get("assumed_live") is True, arale
    assert "assumed_live" not in arale["segs"][0], arale
    print("[OK] _preview_json: assumed_live 플래그가 세그먼트로 전파됨(선행 세그먼트는 제외)")

    # ── _add_minutes: 자정 넘김은 실제 시각으로 wrap(30:00 같은 가짜 시각 아님) ──
    assert _add_minutes("23:59", 3) == "00:02"
    print("[OK] _add_minutes: 자정 넘김 wrap")

    # ── _month_dates: 이번 달 1일~end 날짜까지 오름차순 ──
    assert _month_dates("2026-09-03") == ["2026-09-01", "2026-09-02", "2026-09-03"]
    print("[OK] _month_dates")

    # ── render_html: 플레이스홀더 치환, 유효 JSON 임베드 (days/month/full 구조) ──
    day = {
        "ticks": ticks, "ops": ops, "notice": notice, "relay": [], "tweet": [],
        "preview": preview, "downRanges": [], "vercelPush": 3, "eventCount": len(events),
    }
    report = {"date": "2026-09-15", "full": False, "month": ["2026-09-15"], "days": {"2026-09-15": day}}
    html = render_html(report)
    assert "__REPORT_JSON__" not in html
    assert '"date": "2026-09-15"' in html or '"date":"2026-09-15"' in html
    print("[OK] render_html: 플레이스홀더 치환 완료")

    # ── build_report(full=True): gh mock으로 이번 달 날짜 수만큼 read_text 호출 확인 ──
    class _FullGh:
        def __init__(self):
            self.calls = []
        def read_text(self, path):
            self.calls.append(path)
            return (None, None)  # 아직 로그 없는 날짜(404) — 전부 빈 이벤트로 처리돼야 함

    gh = _FullGh()
    today = datetime.now(KST).strftime("%Y-%m-%d")
    report_full = build_report(gh, full=True)
    expected_days = int(today[8:10])
    assert len(gh.calls) == expected_days, (len(gh.calls), expected_days)
    assert report_full["full"] is True
    assert len(report_full["month"]) == expected_days
    assert report_full["date"] in report_full["days"]
    assert all(report_full["days"][d]["eventCount"] == 0 for d in report_full["month"])
    print("[OK] build_report(full=True): 이번 달 1일~오늘 전부 조회, 없는 날짜는 빈 리포트")

    print("\nSUCCESS: monitor_report.py self-test 통과 (mock)")
