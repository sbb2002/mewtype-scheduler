"""`/monitor` — 실제 모니터링 이벤트 로그(monitor_log.py가 append한 JSONL)를 하루치 모아
Ops Timeline 대시보드 html로 렌더링. push_monitor.py(git 커밋 기반 Vercel 한도 감시)를
대체한다(v3.5, 2026-09-16 세션에서 확정한 1~3단계 스키마 그대로 소비).

이 리포트는 실데이터만 다루므로, 같은 세션에서 만든 Artifact 목업에 있던 아래 기능은
뺐다 — 전부 "재현 근거 데이터가 없어서" 뺀 것이지 귀찮아서가 아니다:
  - 여러 날짜 브라우징(잔디 클릭) — 하루치 이벤트만 담는다. 다른 날짜는
    `/monitor YYYY-MM-DD`로 그날짜를 다시 요청.
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

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
MEMBER_ORDER = ["arale", "yuno", "nonoka", "ritsu", "miyako"]
MEMBER_KO = {"arale": "아라레", "yuno": "유노", "nonoka": "노노카", "ritsu": "리츠", "miyako": "미야코"}


def _kst_hm(iso: str) -> str:
    dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(KST)
    return dt.strftime("%H:%M")


def _add_minutes(hm: str, minutes: int) -> str:
    h, m = map(int, hm.split(":"))
    total = min(h * 60 + m + minutes, 24 * 60)
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
            segs.append({"s": evs[0]["from_state"], "from": "00:00", "to": _kst_hm(evs[0]["ts"])})
        for i, e in enumerate(evs):
            to_state = e.get("to_state")
            title = e.get("title") or title
            seg_from = _kst_hm(e["ts"])
            if i + 1 < len(evs):
                seg_to = _kst_hm(evs[i + 1]["ts"])
            elif to_state == "none":
                seg_to = _add_minutes(seg_from, 3)  # 사라짐은 짧게 표시(실제로 관찰 구간이 없으므로)
            else:
                seg_to = now_hm or "24:00"
            seg = {"s": to_state, "from": seg_from, "to": seg_to}
            if e.get("result") and e["result"] != "ok":
                seg["q"] = e["result"]
                seg["qd"] = e.get("detail", "")
            segs.append(seg)
        out.append({"member": member, "title": title, "segs": segs})
    return out


def _fetch_health_down_ranges(api_key: str, uuid: str, date_kst: str) -> list[dict]:
    """healthchecks.io flips(up/down 이력)에서 이 날짜(KST)의 다운 구간만 HH:MM 범위로 변환.
    키/uuid 없거나 조회 실패하면 빈 리스트(=하루 종일 정상으로 렌더) — 조용히 성능저하."""
    if not api_key or not uuid:
        return []
    day_start = datetime.strptime(date_kst, "%Y-%m-%d").replace(tzinfo=KST)
    day_end = day_start + timedelta(days=1)
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
        ranges.append({"from": down_since, "to": "24:00"})
    return ranges


def _vercel_push_count(github_token: str, date_kst: str) -> int:
    """그날 main 브랜치 push 횟수 — push_monitor.py의 fetch_commits(이미 검증된 코드) 재사용."""
    if not github_token:
        return 0
    from .push_monitor import _CODE_REPO, fetch_commits

    day_start = datetime.strptime(date_kst, "%Y-%m-%d").replace(tzinfo=KST)
    day_end = day_start + timedelta(days=1)
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


def build_report(
    gh, *, date_kst: str | None = None,
    healthchecks_api_key: str = "", healthchecks_uuid: str = "",
    github_token_for_commits: str = "",
) -> dict:
    """오늘(또는 date_kst)치 이벤트 로그 + healthchecks.io + (있으면) 코드 저장소 커밋 수를
    모아 REPORT dict로. gh는 data 저장소용 GitHubStore(text 읽기)."""
    now_kst = datetime.now(KST)
    date_kst = date_kst or now_kst.strftime("%Y-%m-%d")
    now_hm = now_kst.strftime("%H:%M") if date_kst == now_kst.strftime("%Y-%m-%d") else None

    text, _sha = gh.read_text(f"monitoring/events-{date_kst}.jsonl")
    events = parse_events(text)
    grouped = _group(events)

    return {
        "date": date_kst,
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


def run(
    gh, *, date_kst: str | None = None,
    healthchecks_api_key: str = "", healthchecks_uuid: str = "",
    github_token_for_commits: str = "",
) -> dict:
    """`_handle_monitor`/`/monitor` Flask 라우트 진입점. {"html", "date", "events"} 반환."""
    report = build_report(
        gh, date_kst=date_kst, healthchecks_api_key=healthchecks_api_key,
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
    --st-announced:#949494; --st-upcoming:#ffffff; --st-watching:#ffffff;
    --st-live:#ff5470; --st-end:#575757; --st-none:#424242;
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
  .tl-labels{position:relative; flex:0 0 168px; border-right:1px solid var(--line); padding-right:2px}
  .tl-labels .grp{position:absolute; left:0; width:168px; transform:translateY(-50%); font:600 11.5px/1.25 var(--sans);
    color:var(--ink); cursor:pointer; border-bottom:1px dashed transparent}
  .tl-labels .grp:hover{border-color:var(--accent)}
  .tl-labels .row{position:absolute; right:10px; transform:translateY(-50%); font:11px var(--sans); color:var(--muted); white-space:nowrap}
  .tl-scroll{position:relative; overflow-x:auto; overflow-y:hidden; border-radius:0 8px 8px 0; flex:1; min-width:0}
  .tl-scroll.locked{overflow:hidden; touch-action:none}
  #tlSvg{display:block}
  .tl-crosshair{position:absolute; top:0; width:1px; background:rgba(255,255,255,.35); pointer-events:none; display:none; z-index:5}
  .tl-lane{stroke:var(--line); stroke-width:1}
  .tl-hour{stroke:var(--line-soft); stroke-width:1}
  .tl-hour-label{fill:var(--muted-2); font:10px var(--mono)}
  .tl-dot{cursor:pointer; stroke:var(--bg); stroke-width:1.5}
  .tl-dot:hover{stroke:var(--ink)}
  .tl-dot.dim{opacity:.15}
  .tl-trigger-glyph{font-size:18px; pointer-events:none}
  .tl-trigger-glyph.dim{opacity:.15}
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

<div class="tabs" role="tablist">
  <button class="tab-btn active" id="tabBtnApp" role="tab" aria-selected="true">APP</button>
  <button class="tab-btn" id="tabBtnExt" role="tab" aria-selected="false">EXT</button>
</div>

<div id="tabApp">
<section class="stats-row" id="statsRow"></section>

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
    <p class="panel-sub">정기수집·라이브감지 트리거(🕒/📡)가 소모한 quota 누적.</p>
    <div class="ext-gauge-row">
      <div class="stat-tile"><b id="extYtUsed">—</b><span>누적 사용량 / 10,000</span></div>
      <div class="stat-tile"><b id="extYtCalls">—</b><span>API 호출 수(tick+wake)</span></div>
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
const OK = "#7CB342", ERR = "#e5484d", DEGRADED = "#f5c344";
const TONE_COLOR = { ok:OK, degraded:DEGRADED, err:ERR };
const TONE_LABEL = { ok:"정상", degraded:"부분 실패", err:"에러" };
const MEMBER_KO = { arale:"아라레", yuno:"유노", nonoka:"노노카", ritsu:"리츠", miyako:"미야코" };

const PREVIEW = REPORT.preview, TICKS = REPORT.ticks, OPS = REPORT.ops,
      NOTICE = REPORT.notice, TWEET = REPORT.tweet, RELAY = REPORT.relay;

function computeIngest(relay, notice, tweet){
  return [
    ...relay.map(e => ({ t:e.t, source:"공식(BDP_yumemita)", ok:e.tone!=="err", target:{lane:"relay", row:"account"} })),
    ...notice.map(e => ({ t:e.t, source:"공식(BDP_yumemita)", ok:e.tone!=="err", target:{lane:"notice", row:"notice"} })),
    ...tweet.map(e => ({ t:e.t, source:(MEMBER_KO[e.member]||e.member)+" 개인", ok:e.tone!=="err", target:{lane:"tweet", row:e.member} })),
  ];
}
const INGEST = computeIngest(RELAY, NOTICE, TWEET);

const TRIGGER_PRIORITY = { ops:0, ingest:1, tick:2, wake:2 };
const TRIGGER_RADIUS_BASE = 7;
const TRIGGER_RADIUS = 15;
const TRIGGER_FONT_BASE = "12px";
const TRIGGER_FONT_ACTIVE = "18px";
const TRIGGER_OFFSET_STEP = TRIGGER_RADIUS * 2 + 4;
function computeTriggerOffsets(ops, ticks, ingest){
  const byKey = {};
  const points = [
    ...ops.map((e,i) => ({ key:"ops_"+i, t:e.t, kind:"ops" })),
    ...ticks.map((e,i) => ({ key:"tick_"+i, t:e.t, kind:e.kind })),
    ...ingest.map((e,i) => ({ key:"ingest_"+i, t:e.t, kind:"ingest" })),
  ];
  const groups = {};
  points.forEach(p => { (groups[p.t] = groups[p.t] || []).push(p); });
  Object.values(groups).forEach(list => {
    list.sort((a,b) => TRIGGER_PRIORITY[a.kind] - TRIGGER_PRIORITY[b.kind]);
    const n = list.length;
    list.forEach((p,i) => { byKey[p.key] = (i - (n-1)/2) * TRIGGER_OFFSET_STEP; });
  });
  return byKey;
}
const TRIGGER_OFFSET_BY_KEY = computeTriggerOffsets(OPS, TICKS, INGEST);

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
  if (openPause) ranges.push({from:openPause, to:"24:00"});
  return ranges;
}
function computeBackendSegs(ticks, ops, downRanges){
  return buildLayeredSegs([
    { state:"busy",   ranges: ticks.map(e => ({ from:e.t, to:addMinutes(e.t, BACKEND_BUSY_MIN) })) },
    { state:"paused", ranges: pausedRanges(ops) },
    { state:"down",   ranges: downRanges || [] },
  ]);
}
const BACKEND_SEGS = computeBackendSegs(TICKS, OPS, REPORT.downRanges);

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
    { v: `${ytUsed} / 10,000`, s: "YouTube quota 사용(누적)" },
  ];
  document.getElementById("statsRow").innerHTML = tiles.map(t =>
    `<div class="stat-tile${t.err?' error':''}"><b>${t.v}</b><span>${t.s}</span></div>`
  ).join("");
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
  return `<div class="lg-chips">` + Object.entries(STATE).map(([k,v]) => {
    const bg = k === "watching" ? "repeating-linear-gradient(45deg, #ffffff 0 3px, #9aa0a8 3px 6px)" : v.color;
    return `<span class="lg-chip"><i style="background:${bg}"></i>${v.label}</span>`;
  }).join("") + `</div>`;
}
function resultChipsHtml(keys){
  return `<div class="lg-chips">` + keys.map(k =>
    `<span class="lg-chip"><i style="background:${TONE_COLOR[k]}"></i>${TONE_LABEL[k]}</span>`
  ).join("") + `</div>`;
}
function toneChipsHtml(){ return resultChipsHtml(["ok","degraded","err"]); }
function laneLegendHtml(key){
  if (key === "trigger") return `<div class="lg-title">🎯 트리거</div>` +
    `<div class="lg-sub">4가지 트리거를 이모지로 구분, 원 색은 결과.</div>` +
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
    `<div class="lg-sub">굵은 줄 색 = 그 순간 상태(6단계). watching은 upcoming과 같은 흰색이라 빗금으로 구분.</div>` +
    stateChipsHtml() +
    `<div class="lg-sub" style="margin-top:2px">줄 위 작은 점 = 그 전이 자체의 품질</div>` + toneChipsHtml();
  if (key === "relay") return `<div class="lg-title">X 예고 릴레이</div><div class="lg-sub">공식 계정 게시물 파싱 결과.</div>` + toneChipsHtml();
  if (key === "notice") return `<div class="lg-title">소식</div><div class="lg-sub">공식 계정의 방송 외 이벤트 게시물 처리 결과.</div>` + toneChipsHtml();
  if (key === "tweet") return `<div class="lg-title">개인 트윗</div><div class="lg-sub">멤버 개인 트윗 처리 결과.</div>` + toneChipsHtml();
  return "";
}

const ROWS_MEMBERS = ["arale","yuno","nonoka","ritsu","miyako"];
const ROW_H_POINT = 24, ROW_H_BAR = 28, GROUP_GAP = 16, PAD_R = 24, PAD_T = 10, PAD_B = 26;
const BASE_W = 900;
const LANES = [
  { key:"trigger", label:"🎯 트리거", type:"point", rows:["all"], rowH:110 },
  { key:"health",  label:"🖥️ 백엔드 상태", type:"bar", rows:["backend"] },
  { key:"preview", label:"preview (영상 생애주기)", type:"bar",   rows: ROWS_MEMBERS },
  { key:"relay",   label:"X 예고 릴레이",          type:"point", rows:["account"] },
  { key:"notice",  label:"소식",                   type:"point", rows:["notice"] },
  { key:"tweet",   label:"개인 트윗",               type:"point", rows: ROWS_MEMBERS },
];
const TRIGGER_GLYPH = { ops:"🎛️", tick:"🕒", wake:"📡", ingest:"📥" };

let rowY = {};
(function layout(){
  let y = PAD_T;
  LANES.forEach(g => {
    const rh = g.rowH || (g.type === "bar" ? ROW_H_BAR : ROW_H_POINT);
    g._labelY = y + (g.rows.length * rh) / 2;
    g.rows.forEach(r => { rowY[g.key+"|"+r] = y + rh/2; y += rh; });
    y += GROUP_GAP;
  });
  window._TL_H = y - GROUP_GAP + PAD_B;
})();
function minutesOf(hhmm){ const [h,m] = hhmm.split(":").map(Number); return h*60+m; }
function minutesToX(min, plotW){ return (min/1440) * plotW; }
function timeToX(hhmm, plotW){ return minutesToX(minutesOf(hhmm), plotW); }
const NICE_STEPS_MIN = [1,2,5,10,15,30,60,120,180,240,360,720,1440];
const MIN_TICK_PX = 56;
function pickHourStepMin(plotW){
  const pxPerMin = plotW / 1440;
  for (const step of NICE_STEPS_MIN) if (step * pxPerMin >= MIN_TICK_PX) return step;
  return 1440;
}
function fmtHM(min){
  const h = Math.floor(min/60) % 24, m = min % 60;
  return String(h).padStart(2,"0") + ":" + String(m).padStart(2,"0");
}

function renderLabels(){
  const wrap = document.getElementById("tlLabels");
  wrap.style.height = window._TL_H + "px";
  wrap.innerHTML = "";
  LANES.forEach(g => {
    const grp = document.createElement("div");
    grp.className = "grp"; grp.style.top = g._labelY + "px"; grp.textContent = g.label;
    wireLegend(grp, () => laneLegendHtml(g.key));
    wrap.appendChild(grp);
    g.rows.forEach(r => {
      if (!MEMBER_KO[r]) return;
      const row = document.createElement("div");
      row.className = "row"; row.style.top = rowY[g.key+"|"+r] + "px"; row.textContent = MEMBER_KO[r];
      wrap.appendChild(row);
    });
  });
}

const ZOOM_LEVELS = [1, 1.5, 2, 3, 4, 6, 8];
let zoomIdx = 0;
let triggerMarks = [];
function setZoom(idx, clientX){
  const newIdx = Math.max(0, Math.min(ZOOM_LEVELS.length - 1, idx));
  const scrollEl = document.getElementById("tlScroll");
  const rect = scrollEl.getBoundingClientRect();
  const anchorClientX = clientX != null ? clientX : (rect.left + scrollEl.clientWidth / 2);
  const offsetInView = anchorClientX - rect.left;
  const contentX = scrollEl.scrollLeft + offsetInView;
  const oldPlotW = BASE_W * ZOOM_LEVELS[zoomIdx];
  const minutesAtAnchor = (contentX / oldPlotW) * 1440;
  zoomIdx = newIdx;
  document.getElementById("zoomLabel").textContent = Math.round(ZOOM_LEVELS[zoomIdx]*100) + "%";
  renderTimeline();
  const newPlotW = BASE_W * ZOOM_LEVELS[zoomIdx];
  const newContentX = minutesToX(minutesAtAnchor, newPlotW);
  scrollEl.scrollLeft = Math.max(0, newContentX - offsetInView);
}
document.getElementById("zoomIn").addEventListener("click", () => { if (!isPinned()) setZoom(zoomIdx+1); });
document.getElementById("zoomOut").addEventListener("click", () => { if (!isPinned()) setZoom(zoomIdx-1); });
document.getElementById("zoomReset").addEventListener("click", () => { if (!isPinned()) setZoom(0); });
document.getElementById("tlScroll").addEventListener("wheel", (ev) => {
  if (Math.abs(ev.deltaY) < 2) return;
  ev.preventDefault();
  if (isPinned()) return;
  setZoom(zoomIdx + (ev.deltaY < 0 ? 1 : -1), ev.clientX);
}, { passive:false });

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
  const hatch = document.createElementNS(ns, "pattern");
  hatch.setAttribute("id", "watchHatch");
  hatch.setAttribute("width", "6"); hatch.setAttribute("height", "6");
  hatch.setAttribute("patternTransform", "rotate(45)");
  hatch.setAttribute("patternUnits", "userSpaceOnUse");
  const hatchBg = document.createElementNS(ns, "rect");
  hatchBg.setAttribute("width", "6"); hatchBg.setAttribute("height", "6"); hatchBg.setAttribute("fill", "#ffffff");
  hatch.appendChild(hatchBg);
  const hatchStripe = document.createElementNS(ns, "rect");
  hatchStripe.setAttribute("width", "3"); hatchStripe.setAttribute("height", "6"); hatchStripe.setAttribute("fill", "#9aa0a8");
  hatch.appendChild(hatchStripe);
  defs.appendChild(hatch);
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
      rect.setAttribute("x", x1); rect.setAttribute("y", ry - 6);
      rect.setAttribute("width", Math.max(x2-x1, 1)); rect.setAttribute("height", 12);
      rect.setAttribute("rx", 3);
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
      rect.setAttribute("fill", sg.s === "watching" ? "url(#watchHatch)" : (STATE_HEX[sg.s] || "#888"));
      rect.setAttribute("class","tl-seg");
      const q = sg.q || "ok";
      wireTip(rect, { t:sg.from+"–"+sg.to, title:v.title, raw:(STATE[sg.s]||{label:sg.s}).label, tone:"ok", d:sg.qd || ("video: "+(v.title||"—")) });
      svg.appendChild(rect);
      if (!(i === 0 && sg.from === "00:00")) {
        const dot = document.createElementNS(ns,"circle");
        dot.setAttribute("cx", x1); dot.setAttribute("cy", ry);
        dot.setAttribute("r", 3); dot.setAttribute("fill", TONE_COLOR[q]);
        dot.setAttribute("class", "tl-dot" + (activeTones.has(q) ? "" : " dim"));
        wireTip(dot, { t:sg.from, title:v.title, raw:(STATE[sg.s]||{label:sg.s}).label+" 전이 · "+TONE_LABEL[q], tone:q, d:sg.qd || "" });
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
  function drawTriggerDot(t, kind, ok, tipData, offset){
    const x = timeToX(t, plotW);
    const ry = rowY["trigger|all"] + offset;
    const dimmed = !activeTones.has(ok ? "ok" : "err");
    const c = document.createElementNS(ns,"circle");
    c.setAttribute("cx", x); c.setAttribute("cy", ry); c.setAttribute("r", TRIGGER_RADIUS_BASE);
    c.setAttribute("fill", ok ? OK : ERR);
    c.setAttribute("class", "tl-dot" + (dimmed ? " dim" : ""));
    wireTip(c, tipData);
    svg.appendChild(c);
    const txt = document.createElementNS(ns,"text");
    txt.setAttribute("x", x); txt.setAttribute("y", ry);
    txt.setAttribute("text-anchor", "middle"); txt.setAttribute("dominant-baseline", "central");
    txt.setAttribute("class", "tl-trigger-glyph" + (dimmed ? " dim" : ""));
    txt.style.fontSize = TRIGGER_FONT_BASE;
    txt.textContent = TRIGGER_GLYPH[kind];
    wireTip(txt, tipData);
    triggerMarks.push({ x, circle:c, text:txt });
    svg.appendChild(txt);
  }

  OPS.forEach((e, i) => drawTriggerDot(e.t, "ops", e.ok,
    { t:e.t, title:"🎛️ "+e.cmd, raw:e.ok?"ok":"error", tone:e.ok?"ok":"err", d:e.d, _idx:"ops"+i }, TRIGGER_OFFSET_BY_KEY["ops_"+i]));
  TICKS.forEach((e, i) => drawTriggerDot(e.t, e.kind, e.ok,
    { t:e.t, title:(TRIGGER_GLYPH[e.kind]+" ")+(e.mode==="baseline"?"baseline tick":e.mode==="light"?"light tick":"wake"), raw:e.ok?"ok":"error", tone:e.ok?"ok":"err", d:e.d, _idx:"tick"+i }, TRIGGER_OFFSET_BY_KEY["tick_"+i]));
  INGEST.forEach((e, i) => drawTriggerDot(e.t, "ingest", e.ok,
    { t:e.t, title:"📥 "+e.source, raw:e.ok?"ok":"error", tone:e.ok?"ok":"err", d:"→ "+e.target.lane, _idx:"ingest"+i }, TRIGGER_OFFSET_BY_KEY["ingest_"+i]));
  RELAY.forEach((e, i) => drawDot(e.t, rowY["relay|account"], e.tone,
    { t:e.t, title:"BDP_yumemita", raw:TONE_LABEL[e.tone], tone:e.tone, d:e.d, _idx:"relay"+i }));
  NOTICE.forEach((e, i) => drawDot(e.t, rowY["notice|notice"], e.tone,
    { t:e.t, title:"소식", raw:TONE_LABEL[e.tone], tone:e.tone, d:e.d, _idx:"notice"+i }));
  TWEET.forEach((e, i) => drawDot(e.t, rowY["tweet|"+e.member], e.tone,
    { t:e.t, title:(MEMBER_KO[e.member]||e.member)+" 개인 트윗", raw:TONE_LABEL[e.tone], tone:e.tone, d:e.d, _idx:"tweet"+i }));

  document.getElementById("tlSub").textContent =
    "점/막대 위에 마우스를 올리면 시간·제목·결과가 보이고, 클릭하면 아래 표의 해당 행으로 이동합니다.";
}

const STATE_HEX = { announced:"#949494", upcoming:"#ffffff", watching:"#ffffff", live:"#ff5470", end:"#575757", none:"#424242" };

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
  if (!document.getElementById("tooltip").contains(ev.target)) unpinTip();
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
    m.circle.setAttribute("r", active ? TRIGGER_RADIUS : TRIGGER_RADIUS_BASE);
    m.text.style.fontSize = active ? TRIGGER_FONT_ACTIVE : TRIGGER_FONT_BASE;
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
      const skip = i === 0 && sg.from === "00:00";
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

document.getElementById("lede").innerHTML =
  `<b>${REPORT.date}</b> 하루치 — 운영자 제어·정기수집 틱·X 웹훅 인입(트리거) → preview·릴레이·소식·개인 트윗(결과)을 같은 시간축에서 대조합니다. ` +
  `다른 날짜는 <code>/monitor YYYY-MM-DD</code>로 요청하세요.`;
document.getElementById("tlTitle").textContent = REPORT.date + " · 24시간 타임라인";
renderStats();
renderLabels();
renderTimeline();
renderTable();
document.getElementById("footer").textContent =
  `생성 기준: ${REPORT.date} · 총 ${REPORT.eventCount || 0}건 기록 · Ops Monitor(구 Push Monitor)`;

(function setupCrosshair(){
  const scrollEl = document.getElementById("tlScroll");
  const crosshair = document.getElementById("tlCrosshair");
  function moveTo(clientX){
    const rect = scrollEl.getBoundingClientRect();
    const x = clientX - rect.left + scrollEl.scrollLeft;
    crosshair.style.left = x + "px";
    crosshair.style.height = (document.getElementById("tlSvg").getAttribute("height") || 0) + "px";
    crosshair.style.display = "block";
    setTriggerActiveNear(x);
  }
  scrollEl.addEventListener("mousemove", (ev) => moveTo(ev.clientX));
  scrollEl.addEventListener("mouseleave", () => { crosshair.style.display = "none"; setTriggerActiveNear(null); });
  scrollEl.addEventListener("click", (ev) => { if (!isPinned()) moveTo(ev.clientX); });
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
  cap.textContent = `누적 ${cum} units (${REPORT.date})`;
  svg.appendChild(cap);
  [0,6,12,18,24].forEach(h => {
    const t = document.createElementNS(ns,"text");
    t.setAttribute("x", px(h*60)); t.setAttribute("y", H-4);
    t.setAttribute("fill","#5f6570"); t.setAttribute("font-size","10");
    t.setAttribute("text-anchor", h===0?"start":h===24?"end":"middle");
    t.textContent = String(h).padStart(2,"0")+":00";
    svg.appendChild(t);
  });
}
renderExtYoutube();

function renderExtVercel(){
  const push = REPORT.vercelPush || 0;
  const overLimit = push > 100;
  document.getElementById("extVercelUsed").textContent = push + " / 100";
  document.getElementById("extVercelStatus").textContent = overLimit ? "한도 초과 위험" : "정상";
  document.getElementById("extVercelTile").classList.toggle("error", overLimit);
}
renderExtVercel();
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
        '"from_state":"upcoming","to_state":"watching","title":"통상방송"}\n'
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

    # ── _preview_json: from_state 있는 첫 이벤트 → 선행 세그먼트, 없으면 생략 ──
    preview = _preview_json(grouped["preview"], now_hm="12:00")
    arale = next(v for v in preview if v["member"] == "arale")
    assert arale["segs"][0]["s"] == "upcoming" and arale["segs"][0]["from"] == "00:00", arale
    assert arale["segs"][1]["s"] == "watching" and arale["segs"][1]["to"] == "12:00", arale
    ritsu = next(v for v in preview if v["member"] == "ritsu")
    assert ritsu["segs"] == [], "이벤트 없는 멤버는 빈 세그먼트"
    print("[OK] _preview_json: 선행 세그먼트(from_state) + 마지막 세그먼트는 now_hm까지")

    # ── render_html: 플레이스홀더 치환, 유효 JSON 임베드 ──
    report = {
        "date": "2026-09-15", "ticks": ticks, "ops": ops, "notice": notice, "relay": [],
        "tweet": [], "preview": preview, "downRanges": [], "vercelPush": 3, "eventCount": len(events),
    }
    html = render_html(report)
    assert "__REPORT_JSON__" not in html
    assert '"date": "2026-09-15"' in html or '"date":"2026-09-15"' in html
    print("[OK] render_html: 플레이스홀더 치환 완료")

    print("\nSUCCESS: monitor_report.py self-test 통과 (mock)")
