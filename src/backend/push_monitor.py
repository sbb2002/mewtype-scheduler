"""push 모니터 대시보드 — data/main 브랜치 커밋(=Vercel 배포 시도) 활동 시각화.

배경: 2026-09-13 Vercel Hobby 플랜 "하루 100회 배포" 한도 초과 사고(VERSION.md
v3.2.2 참고) — `vercel.json` 위치 버그로 `data` 브랜치의 봇 커밋이 전부 배포
시도로 잡혀 소진됐다. 재발 조기 감지용으로 최근 N일 커밋 활동을 카테고리별
누적 막대(10분 단위)로 보여주는 정적 대시보드를 매시간 생성해 `devpapers`
브랜치(`docs/PUSH_MONITOR.html`)에 커밋한다 — `data` 브랜치와 같은 이유로
Vercel 배포 트리거 밖에 둔다.

순수 함수(categorize/build_dashboard_data/render_html)와 네트워크 I/O
(fetch_commits/run)를 분리. self-test: python -m src.backend.push_monitor
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

KST = timezone(timedelta(hours=9))
_BIN_MINUTES = 10
_BINS_PER_DAY = 24 * 60 // _BIN_MINUTES

# ── 카테고리 정의 ──────────────────────────────────────────────────────
_MANUAL_MARKERS = ("manual add", "잘린 URL 정리", "제목 번역(title_ko) 소급", "수동 보정")

_DATA_PREFIXES = [
    ("preview", "data: preview"),
    ("tweet", "data: tweet"),
    ("notice", "data: notice"),
    ("undo_snapshot", "data: undo snapshot"),
    ("personal_schedule", "data: personal schedule"),
    ("xrelay", "data: xrelay"),
]

CATEGORY_LABELS = {
    "preview": "preview (정기 tick/wake)",
    "tweet": "tweet (개인 트윗 ingest)",
    "notice": "notice (소식 ingest)",
    "undo_snapshot": "undo snapshot",
    "personal_schedule": "personal schedule",
    "xrelay": "xrelay scheduled",
    "manual": "수동 패치",
    "other_data": "기타(data)",
    "code_main": "코드(main)",
}
CATEGORY_ORDER = [
    "preview", "tweet", "notice", "undo_snapshot", "personal_schedule",
    "xrelay", "manual", "other_data", "code_main",
]
CATEGORY_COLORS = {
    "preview": "#4C78A8",
    "tweet": "#F58518",
    "notice": "#54A24B",
    "undo_snapshot": "#E45756",
    "personal_schedule": "#72B7B2",
    "xrelay": "#B279A2",
    "manual": "#FF9DA6",
    "other_data": "#BAB0AC",
    "code_main": "#D8DCE0",
}


def categorize(branch: str, message: str) -> str:
    """(branch, 커밋 메시지 첫 줄) → 카테고리 키."""
    if branch != "data":
        return "code_main"
    if any(k in message for k in _MANUAL_MARKERS):
        return "manual"
    for cat, prefix in _DATA_PREFIXES:
        if message.startswith(prefix):
            return cat
    return "other_data"


def _to_kst(iso_utc: str) -> datetime:
    return datetime.fromisoformat(iso_utc.replace("Z", "+00:00")).astimezone(KST)


def build_dashboard_data(records: list[dict], *, now_kst: datetime, days: int) -> dict:
    """records: [{"branch": "data"|"main", "date": <ISO UTC>, "message": <첫 줄>}, ...]

    Returns:
        {"generated_at", "days": [{"date","total","by_cat"}, ...],
         "detail": {date: [ {cat: count} x144 bins ]}, "categories": [...]}
    """
    start_date = (now_kst - timedelta(days=days - 1)).date()
    day_totals: dict[str, dict[str, int]] = {}
    detail: dict[str, list[dict[str, int]]] = {}
    events: dict[str, list[dict]] = {}

    def ensure_day(d: str) -> None:
        if d not in day_totals:
            day_totals[d] = {c: 0 for c in CATEGORY_ORDER}
            detail[d] = [{c: 0 for c in CATEGORY_ORDER} for _ in range(_BINS_PER_DAY)]
            events[d] = []

    for r in records:
        try:
            ts = _to_kst(r["date"])
        except (ValueError, KeyError, AttributeError):
            continue
        d = ts.date()
        if d < start_date:
            continue
        d_str = d.isoformat()
        ensure_day(d_str)
        cat = categorize(r.get("branch", ""), r.get("message", ""))
        day_totals[d_str][cat] += 1
        bin_idx = (ts.hour * 60 + ts.minute) // _BIN_MINUTES
        detail[d_str][bin_idx][cat] += 1
        events[d_str].append({
            "bin": bin_idx, "time": ts.strftime("%H:%M:%S"), "cat": cat,
            "message": r.get("message", ""),
        })

    days_list = []
    for i in range(days):
        d = (start_date + timedelta(days=i)).isoformat()
        ensure_day(d)
        events[d].sort(key=lambda e: e["time"])
        days_list.append({
            "date": d,
            "total": sum(day_totals[d].values()),
            "by_cat": day_totals[d],
        })

    return {
        "generated_at": now_kst.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "year": now_kst.year,
        "days": days_list,
        "detail": detail,
        "events": events,
        "categories": [
            {"key": c, "label": CATEGORY_LABELS[c], "color": CATEGORY_COLORS[c]}
            for c in CATEGORY_ORDER
        ],
    }


# ── 장기 이력(수치 집계만 누적, 원본 커밋은 저장 안 함) ──────────────────────
_HISTORY_PATH = "docs/push_monitor_history.json"


def merge_history(history: dict, days_list: list[dict]) -> dict:
    """최근 집계(build_dashboard_data 의 days_list)를 history(날짜→카테고리별 건수)에
    덮어쓰기 병합. 매 실행마다 전체 기간을 재조회하지 않고도 분기 비교 등에 쓸 장기
    데이터가 쌓이도록 하기 위함 — 저장되는 건 집계 수치뿐, 원본 커밋 메시지 아님."""
    merged = dict(history)
    for d in days_list:
        merged[d["date"]] = d["by_cat"]
    return merged


def history_to_days_list(history: dict) -> list[dict]:
    """history(날짜→카테고리별 건수) → build_dashboard_data 의 days_list 와 같은 형식,
    날짜 오름차순."""
    return [
        {"date": d, "total": sum(history[d].values()), "by_cat": history[d]}
        for d in sorted(history)
    ]


# ── HTML 렌더 ──────────────────────────────────────────────────────────
_TEMPLATE = r"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Push Monitor</title>
<style>
  :root{color-scheme:dark;--bg:#0d0e12;--panel:#15161a;--line:#2a2c33;--ink:#e8e8e8;
        --muted:#8a8f98;--accent:#7dd3c0}
  body{background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,"Segoe UI",Inter,sans-serif;
       padding:24px 20px 60px;max-width:1320px;margin:0 auto}
  h1{font-size:1.3rem;margin:0 0 4px}
  .sub{color:var(--muted);font-size:.85rem;margin:0 0 22px}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:20px}
  .legend{display:flex;flex-wrap:wrap;gap:10px 16px;font-size:.78rem;color:var(--muted);margin-top:14px}
  .legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
  .year-nav{display:flex;align-items:center;gap:10px;margin-bottom:10px}
  .year-label{font-weight:600;font-size:.95rem}
  .year-btn{background:none;border:1px solid var(--line);color:var(--ink);border-radius:6px;
            width:26px;height:26px;cursor:pointer;font-size:.75rem;line-height:1;padding:0;
            transition:border-color .15s ease,background-color .15s ease,transform .08s ease}
  .year-btn:hover{border-color:var(--accent)}
  .year-btn:active{transform:scale(.9)}
  .today-btn{width:auto;padding:0 10px}
  .year-grid{display:flex;flex-direction:column;gap:3px}
  .month-row{display:flex;align-items:center;gap:8px}
  .month-row .m-label{width:30px;flex:none;text-align:right;color:var(--muted);font-size:.72rem}
  .month-row .days{display:flex;gap:3px;flex-wrap:wrap}
  .month-row .cell{width:14px;height:14px;border-radius:3px;cursor:pointer;border:1px solid transparent;flex:none;
                    transition:background-color .25s ease,outline-color .15s ease}
  .month-row .cell.sel{outline:2px solid #4da3ff;outline-offset:1px}
  .month-row .cell:hover{border-color:#fff}
  .detail-title{font-size:1rem;margin:0 0 2px}
  .detail-sub{color:var(--muted);font-size:.8rem;margin:0 0 14px}
  .chart-wrap{position:relative;overflow-x:auto}
  svg{display:block}
  .bar{cursor:pointer;transition:height .3s ease,y .3s ease,width .3s ease}
  .xaxis text{fill:var(--muted);font-size:11px}
  .tooltip{position:fixed;background:#1c1e24;border:1px solid var(--line);border-radius:8px;
           padding:8px 10px;font-size:.76rem;pointer-events:none;z-index:50;display:none;
           box-shadow:0 6px 20px rgba(0,0,0,.4);max-width:260px}
  .tooltip .t-time{color:var(--muted);margin-bottom:4px}
  .tooltip .t-row{display:flex;justify-content:space-between;gap:14px;align-items:center}
  .tooltip .t-row b{color:var(--ink)}
  .tooltip .t-cmp{color:var(--muted);font-size:.68rem;margin-top:4px}
  .swatch{display:inline-block;width:9px;height:9px;border-radius:2px;margin-right:5px;vertical-align:-1px;flex:none}
  .events-table{width:100%;border-collapse:collapse;font-size:.8rem;margin-top:16px;table-layout:fixed}
  .events-table th,.events-table td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .events-table th{color:var(--muted);font-weight:normal}
  .events-table col.c-swatch{width:26px}
  .events-table col.c-time{width:78px}
  .events-table col.c-cat{width:170px}
  .events-table col.c-target{width:auto}
  .empty{color:var(--muted);text-align:center;padding:30px 0}
  footer{color:var(--muted);font-size:.75rem;margin-top:30px;text-align:center}
  .layout{display:grid;grid-template-columns:6fr 4fr;gap:20px;align-items:start}
  @media (max-width:900px){.layout{grid-template-columns:1fr}}
  .year-panel-body{display:flex;gap:8px;align-items:flex-start;flex-wrap:wrap}
  .month-chart-col{flex:1 1 200px;min-width:180px}
  .chart-mini-title{font-size:.82rem;margin:0 0 8px;color:var(--muted);font-weight:600}
  .events-collapse{overflow:hidden;max-height:0;transition:max-height .35s ease}
  .summary-legend{display:flex;flex-direction:column;gap:3px;font-size:.68rem;color:var(--muted);margin-top:8px}
  .summary-legend .empty-inline{color:var(--muted)}
  .donut-wrap{display:flex;gap:20px;align-items:center;flex-wrap:wrap;margin-bottom:16px}
  .donut-total{font-size:.78rem;color:var(--muted);text-align:center}
  .donut-total b{display:block;font-size:1.3rem;color:var(--ink)}
  .section-h{font-size:.85rem;color:var(--muted);margin:16px 0 6px}
  .summary-table{width:100%;border-collapse:collapse;font-size:.8rem}
  .summary-table th,.summary-table td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:left}
  .summary-table th{color:var(--muted);font-weight:normal}
  .summary-table td.num{text-align:right}
</style>
</head>
<body>
<h1>Push Monitor</h1>
<p class="sub">data/main 브랜치 커밋(=Vercel 배포 시도) 활동 — Hobby 플랜 하루 100건 한도 재소진 조기 감지용.
날짜 칸을 클릭하면 그 날의 10분 단위 상세를 아래에서 봅니다.</p>

<div class="layout">
<div class="col-left">

<div class="panel">
  <div class="year-nav">
    <button class="year-btn" id="yearPrev" aria-label="이전 연도">◀</button>
    <span class="year-label" id="yearLabel"></span>
    <button class="year-btn" id="yearNext" aria-label="다음 연도">▶</button>
    <button class="year-btn today-btn" id="todayBtn">TODAY</button>
  </div>
  <h3 class="chart-mini-title" id="summaryTitle">—</h3>
  <div class="year-panel-body">
    <div class="year-grid" id="yearGrid"></div>
    <div class="month-chart-col">
      <div class="chart-wrap"><svg id="summaryChart" preserveAspectRatio="none"></svg></div>
      <div class="summary-legend" id="summaryLegend"></div>
    </div>
  </div>
</div>

<div class="panel">
  <h2 class="detail-title" id="detailTitle">—</h2>
  <p class="detail-sub" id="detailSub"></p>
  <div class="chart-wrap"><svg id="chart" width="1040" height="320"></svg></div>
  <div class="legend" id="legend"></div>
  <div id="detailEvents" class="events-collapse"></div>
</div>

</div>
<div class="col-right">

<div class="panel">
  <h2 class="detail-title" id="summaryTableTitle">—</h2>
  <div class="donut-wrap">
    <svg id="donut" viewBox="0 0 140 140" width="140" height="140"></svg>
    <div class="donut-total" id="donutTotal"></div>
  </div>
  <div class="section-h">카테고리별 건수</div>
  <table class="summary-table" id="catSummaryTable"></table>
  <div class="section-h">Vercel 배포 한도(200/일) 초과일</div>
  <table class="summary-table" id="overLimitTable"></table>
</div>

</div>
</div>

<footer id="footer"></footer>
<div class="tooltip" id="tooltip"></div>

<script>
const DATA = __DATA_JSON__;

const legend = document.getElementById("legend");
DATA.categories.forEach(c => {
  const span = document.createElement("span");
  span.innerHTML = `<i style="background:${c.color}"></i>${c.label}`;
  legend.appendChild(span);
});

document.getElementById("footer").textContent = "마지막 갱신: " + DATA.generated_at.replace("T"," ").slice(0,16) + " KST (1시간 주기 자동 갱신)";

// ── 잔디(연간 월별 그리드) ──
const VERCEL_LIMIT = 200;
const byDateRec = {};
DATA.days.forEach(d => { byDateRec[d.date] = d; });

const yearGrid = document.getElementById("yearGrid");
const dayTotals = {};
DATA.days.forEach(d => { dayTotals[d.date] = d.total; });
const maxTotal = Math.max(1, ...DATA.days.map(d => d.total));
function heatColor(dateStr) {
  const rec = byDateRec[dateStr];
  const total = rec ? rec.total : 0;
  if (total === 0) return "#1c1e24";
  const t = Math.min(1, total / maxTotal);
  const light = 18 + t * 42; // 18% ~ 60%
  if ((rec.by_cat.code_main || 0) > VERCEL_LIMIT) return `hsl(355, 70%, ${light}%)`; // 한도 초과 → 빨간 계통
  return `hsl(175, 55%, ${light}%)`; // 단일 색상(teal) 명도만 증가 — 값이 클수록 밝게, GitHub 잔디 스타일.
}
let selectedDate = DATA.days.length ? DATA.days[DATA.days.length - 1].date : null;
let currentYear = DATA.year;

function buildYearGrid() {
  yearGrid.innerHTML = "";
  document.getElementById("yearLabel").textContent = currentYear + "년";
  const year = currentYear;
  for (let m = 1; m <= 12; m++) {
    const daysInMonth = new Date(year, m, 0).getDate();
    const row = document.createElement("div");
    row.className = "month-row";
    const label = document.createElement("span");
    label.className = "m-label";
    label.textContent = m + "월";
    row.appendChild(label);
    const daysWrap = document.createElement("div");
    daysWrap.className = "days";
    for (let day = 1; day <= daysInMonth; day++) {
      const dateStr = `${year}-${String(m).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
      const total = dayTotals[dateStr] || 0;
      const cell = document.createElement("div");
      cell.className = "cell" + (dateStr === selectedDate ? " sel" : "");
      cell.style.background = heatColor(dateStr);
      cell.addEventListener("mousemove", (ev) => showTipHTML(ev,
        `<div class="t-time">${dateStr}</div><div class="t-row"><span>커밋</span><b>${total}건</b></div>`));
      cell.addEventListener("mouseleave", hideTip);
      cell.addEventListener("click", () => {
        selectedDate = dateStr;
        buildYearGrid();
        renderDetail();
        updateRightPanels();
      });
      daysWrap.appendChild(cell);
    }
    row.appendChild(daysWrap);
    yearGrid.appendChild(row);
  }
}
document.getElementById("yearPrev").addEventListener("click", () => { currentYear -= 1; buildYearGrid(); updateRightPanels(); });
document.getElementById("yearNext").addEventListener("click", () => { currentYear += 1; buildYearGrid(); updateRightPanels(); });
document.getElementById("todayBtn").addEventListener("click", () => {
  const todayStr = DATA.generated_at.slice(0, 10);
  currentYear = Number(todayStr.slice(0, 4));
  selectedDate = todayStr;
  buildYearGrid();
  renderDetail();
  updateRightPanels();
});
buildYearGrid();

// ── 상세 차트 ──
const svg = document.getElementById("chart");
const tooltip = document.getElementById("tooltip");
const W = 1040, H = 320, PAD_L = 40, PAD_B = 30, PAD_T = 10;
const plotW = W - PAD_L - 10, plotH = H - PAD_T - PAD_B;

// 막대를 baseline 에서 최종 높이로 자라나게(CSS transition, .bar 참고)
function growBar(rect, finalY, finalH, baseline) {
  rect.setAttribute("y", baseline);
  rect.setAttribute("height", 0);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      rect.setAttribute("y", finalY);
      rect.setAttribute("height", finalH);
    });
  });
}
// 가로 막대용 — x 는 고정, width 만 0 → 최종값으로 자라남
function growBarW(rect, finalW) {
  rect.setAttribute("width", 0);
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      rect.setAttribute("width", finalW);
    });
  });
}

function renderDetail() {
  const day = DATA.days.find(d => d.date === selectedDate);
  const bins = DATA.detail[selectedDate] || [];
  document.getElementById("detailTitle").textContent = selectedDate || "—";
  document.getElementById("detailSub").textContent = day ? `총 ${day.total}건` : "데이터 없음";
  svg.innerHTML = "";
  document.getElementById("detailEvents").innerHTML = "";
  if (!bins.length || !day || day.total === 0) {
    const t = document.createElementNS("http://www.w3.org/2000/svg", "text");
    t.setAttribute("x", W/2); t.setAttribute("y", H/2);
    t.setAttribute("text-anchor", "middle"); t.setAttribute("fill", "#8a8f98");
    t.textContent = "이 날짜엔 커밋이 없습니다";
    svg.appendChild(t);
    return;
  }
  const totals = bins.map(b => DATA.categories.reduce((s,c) => s + (b[c.key]||0), 0));
  const maxY = Math.max(1, ...totals);
  const barW = plotW / bins.length;

  const ns = "http://www.w3.org/2000/svg";
  const g = document.createElementNS(ns, "g");
  bins.forEach((b, i) => {
    let y0 = 0;
    DATA.categories.forEach(c => {
      const v = b[c.key] || 0;
      if (v === 0) return;
      const h = (v / maxY) * plotH;
      const rect = document.createElementNS(ns, "rect");
      rect.setAttribute("x", PAD_L + i * barW);
      rect.setAttribute("width", Math.max(barW - 0.4, 0.6));
      rect.setAttribute("fill", c.color);
      rect.classList.add("bar");
      rect.addEventListener("mousemove", (ev) => showTip(ev, i, b, totals[i]));
      rect.addEventListener("mouseleave", hideTip);
      rect.addEventListener("click", () => renderEventsTable(i));
      g.appendChild(rect);
      growBar(rect, PAD_T + plotH - (y0 + h), h, PAD_T + plotH);
      y0 += h;
    });
    // 빈 bin 도 호버/클릭 가능하게 투명 히트 영역
    if (totals[i] === 0) {
      const hit = document.createElementNS(ns, "rect");
      hit.setAttribute("x", PAD_L + i * barW);
      hit.setAttribute("y", PAD_T);
      hit.setAttribute("width", Math.max(barW - 0.4, 0.6));
      hit.setAttribute("height", plotH);
      hit.setAttribute("fill", "transparent");
      hit.classList.add("bar");
      hit.addEventListener("mousemove", (ev) => showTip(ev, i, b, 0));
      hit.addEventListener("mouseleave", hideTip);
      hit.addEventListener("click", () => renderEventsTable(i));
      g.appendChild(hit);
    }
  });
  svg.appendChild(g);

  // x축 (2시간 간격)
  const axis = document.createElementNS(ns, "g");
  axis.setAttribute("class", "xaxis");
  for (let h = 0; h <= 24; h += 2) {
    const i = h * 6; // 10분 bin 기준
    const x = PAD_L + Math.min(i, bins.length) * barW;
    const t = document.createElementNS(ns, "text");
    t.setAttribute("x", x); t.setAttribute("y", H - 10);
    t.textContent = String(h).padStart(2,"0") + ":00";
    axis.appendChild(t);
  }
  svg.appendChild(axis);

  // y축 안내선
  const yline = document.createElementNS(ns, "line");
  yline.setAttribute("x1", PAD_L); yline.setAttribute("x2", PAD_L);
  yline.setAttribute("y1", PAD_T); yline.setAttribute("y2", PAD_T + plotH);
  yline.setAttribute("stroke", "#2a2c33");
  svg.appendChild(yline);
}

function showTipHTML(ev, html) {
  tooltip.innerHTML = html;
  tooltip.style.display = "block";
  tooltip.style.left = (ev.clientX + 14) + "px";
  tooltip.style.top = (ev.clientY + 14) + "px";
}
function showTip(ev, binIdx, bin, total) {
  const hh = String(Math.floor(binIdx / 6)).padStart(2, "0");
  const mm = String((binIdx % 6) * 10).padStart(2, "0");
  let rows = "";
  DATA.categories.forEach(c => {
    const v = bin[c.key] || 0;
    if (v > 0) rows += `<div class="t-row"><span><i class="swatch" style="background:${c.color}"></i>${c.label}</span><b>${v}</b></div>`;
  });
  showTipHTML(ev, `<div class="t-time">${selectedDate} ${hh}:${mm} (총 ${total}건)</div>` +
    (rows || '<div class="t-row"><span>변화 없음</span></div>'));
}
function hideTip() { tooltip.style.display = "none"; }

function renderEventsTable(binIdx) {
  const wrap = document.getElementById("detailEvents");
  const hh = String(Math.floor(binIdx / 6)).padStart(2, "0");
  const mm = String((binIdx % 6) * 10).padStart(2, "0");
  const evs = (DATA.events[selectedDate] || [])
    .filter(e => e.bin === binIdx)
    .slice()
    .sort((a, b) => a.time.localeCompare(b.time));
  if (!evs.length) {
    wrap.innerHTML = `<p class="detail-sub">${hh}:${mm} 구간엔 이벤트가 없습니다</p>`;
  } else {
    const rows = evs.map(e => {
      const c = DATA.categories.find(x => x.key === e.cat) || { label: e.cat, color: "#888" };
      const target = (e.message || "").replace(/^data:\s*/, "").trim();
      return `<tr><td><i class="swatch" style="background:${c.color}"></i></td><td>${e.time}</td><td>${c.label}</td><td title="${target.replace(/"/g,"&quot;")}">${target}</td></tr>`;
    }).join("");
    wrap.innerHTML = `<table class="events-table">` +
      `<colgroup><col class="c-swatch"><col class="c-time"><col class="c-cat"><col class="c-target"></colgroup>` +
      `<thead><tr><th></th><th>시각</th><th>항목</th><th>대상</th></tr></thead>` +
      `<tbody>${rows}</tbody></table>`;
  }
  // 펼치기 애니메이션: 0 → 실제 콘텐츠 높이
  wrap.style.maxHeight = "0px";
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      wrap.style.maxHeight = wrap.scrollHeight + "px";
    });
  });
}

// ── 잔디 옆: 해당 연도 월별 배포 추이 + 우측: 요약(도넛/카테고리/초과일) ──
const summarySvg = document.getElementById("summaryChart");
const SW = 240;

function yearDates(year) {
  const out = [];
  for (let m = 1; m <= 12; m++) {
    const dim = new Date(year, m, 0).getDate();
    for (let d = 1; d <= dim; d++) out.push(`${year}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`);
  }
  return out;
}

// 분기의 "월별 총계 평균" — 막대(월별 합계)와 같은 단위라 한 눈에 비교 가능.
// 해당 분기에 기록된 달이 하나도 없으면 null(표시 안 함).
function quarterMonthlyAvg(year, q) {
  const months = [];
  for (let m = (q - 1) * 3 + 1; m <= (q - 1) * 3 + 3; m++) {
    const dim = new Date(year, m, 0).getDate();
    let sum = 0, any = false;
    for (let d = 1; d <= dim; d++) {
      const ds = `${year}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      if (byDateRec[ds]) { any = true; sum += byDateRec[ds].by_cat.code_main || 0; }
    }
    if (any) months.push(sum);
  }
  if (months.length === 0) return null;
  return months.reduce((a, b) => a + b, 0) / months.length;
}

function updateRightPanels() {
  renderSummaryChart();
  renderSummaryTables();
}

function renderSummaryChart() {
  const ns = "http://www.w3.org/2000/svg";

  // 잔디(year-grid)의 실제 렌더 높이를 그대로 재서 12개 행 피치를 맞춘다 —
  // 왼쪽 잔디의 1월~12월 행과 오른쪽 막대가 정확히 같은 y 위치에 오도록.
  const gridH = yearGrid.getBoundingClientRect().height || 204;
  const ROW_H = gridH / 12;
  const rows = [];
  for (let m = 1; m <= 12; m++) {
    const dim = new Date(currentYear, m, 0).getDate();
    const catSums = {}; DATA.categories.forEach(c => catSums[c.key] = 0);
    for (let d = 1; d <= dim; d++) {
      const ds = `${currentYear}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
      const rec = byDateRec[ds];
      if (rec) DATA.categories.forEach(c => { catSums[c.key] += rec.by_cat[c.key] || 0; });
    }
    const total = Object.values(catSums).reduce((a, b) => a + b, 0);
    rows.push({ catSums, total, codeMain: catSums.code_main, month: m, tip: `${currentYear}-${String(m).padStart(2, "0")}` });
  }

  // 이번 분기가 전년도 동분기 대비 얼마나 push 중인지 한눈에 보이도록,
  // 분기별 월평균 값(코드 배포=code_main 기준)에 세로 점선을 긋는다 — 각 분기 점선은
  // 그 분기가 속한 3개월 행 구간에서만 그려지는 끊어진 선(연속선 아님). 데이터 없는 분기는 생략.
  const QUARTER_COLORS = { 1: "#F88379", 2: "#ADCBE2", 3: "#D3A97F", 4: "#FFFFFF" };
  const refLines = [];
  [currentYear - 1, currentYear].forEach(year => {
    const opacity = year === currentYear ? 1 : 0.4;
    for (let q = 1; q <= 4; q++) {
      const avg = quarterMonthlyAvg(year, q);
      if (avg !== null) refLines.push({ year, q, value: avg, color: QUARTER_COLORS[q], opacity });
    }
  });

  const maxX = Math.max(1, ...rows.map(r => r.total), ...refLines.map(rl => rl.value)) * 1.1;
  const PT = 0, PL = 6, PR = 10; // 위(PT)=0 — 잔디 1월 행과 정확히 같은 높이에서 시작. 라벨 없앤 만큼 PL 최소화
  const plotW = SW - PL - PR;
  const plotH = rows.length * ROW_H;
  const totalH = PT + plotH;
  summarySvg.setAttribute("viewBox", `0 0 ${SW} ${totalH}`);
  // width 는 칼럼 폭에 맞춰 100%로 늘어나고, height 는 잔디 실측 높이(gridH)로 고정 —
  // preserveAspectRatio="none" 이라 위아래로 레터박싱되지 않고 정확히 그 높이를 채운다.
  summarySvg.setAttribute("width", "100%");
  summarySvg.style.height = totalH + "px";
  summarySvg.innerHTML = "";

  document.getElementById("summaryTitle").textContent = `${currentYear}년 배포 추이(월별)`;

  const ROW_PAD = ROW_H * 0.2; // 막대끼리 달라붙지 않게 칸마다 위아래 여백
  const barH = Math.max(ROW_H - ROW_PAD * 2, 1);
  const RADIUS = Math.min(3, barH / 2);

  function rowTooltip(r) {
    const q = Math.ceil(r.month / 3);
    const catRows = DATA.categories
      .filter(c => (r.catSums[c.key] || 0) > 0)
      .map(c => `<div class="t-row"><span><i class="swatch" style="background:${c.color}"></i>${c.label}</span><b>${r.catSums[c.key]}건</b></div>`)
      .join("");
    const cmpRows = refLines.filter(rl => rl.q === q).map(rl => {
      const diff = r.codeMain - rl.value;
      const pct = rl.value !== 0 ? (diff / rl.value) * 100 : 0;
      const sign = diff >= 0 ? "+" : "";
      const who = rl.year === currentYear ? "당해년도" : "전년도";
      return `<div class="t-cmp">${who} 동일분기 대비 ${sign}${diff.toFixed(0)}건(${sign}${pct.toFixed(2)}%)</div>`;
    }).join("");
    return `<div class="t-time">${r.tip}</div>${catRows}` +
      `<div class="t-row"><span>합계</span><b>${r.total}건</b></div>${cmpRows}`;
  }

  const defs = document.createElementNS(ns, "defs");
  summarySvg.appendChild(defs);
  const g = document.createElementNS(ns, "g");
  rows.forEach((r, i) => {
    const totalW = Math.max((r.total / maxX) * plotW, r.total > 0 ? 1 : 0);
    const y = PT + i * ROW_H;

    // 막대 전체를 둥근 사각형 클립으로 감싸서 범례별 누적 구간을 이어붙인다 —
    // 각 구간마다 rx 를 주면 이음매가 지저분해지므로 바깥 테두리만 둥글게.
    const clipId = `bar-clip-${i}`;
    const clipRect = document.createElementNS(ns, "rect");
    clipRect.setAttribute("x", PL); clipRect.setAttribute("y", y + ROW_PAD);
    clipRect.setAttribute("width", 0); clipRect.setAttribute("height", barH);
    clipRect.setAttribute("rx", RADIUS); clipRect.setAttribute("ry", RADIUS);
    const clip = document.createElementNS(ns, "clipPath");
    clip.setAttribute("id", clipId);
    clip.appendChild(clipRect);
    defs.appendChild(clip);

    const segG = document.createElementNS(ns, "g");
    segG.setAttribute("clip-path", `url(#${clipId})`);
    let xOff = PL;
    DATA.categories.forEach(c => {
      const v = r.catSums[c.key] || 0;
      if (v <= 0) return;
      const w = (v / maxX) * plotW;
      const seg = document.createElementNS(ns, "rect");
      seg.setAttribute("x", xOff); seg.setAttribute("y", y + ROW_PAD);
      seg.setAttribute("width", w); seg.setAttribute("height", barH);
      seg.setAttribute("fill", c.color);
      segG.appendChild(seg);
      xOff += w;
    });
    g.appendChild(segG);

    const hit = document.createElementNS(ns, "rect");
    hit.setAttribute("x", PL); hit.setAttribute("y", y);
    hit.setAttribute("width", plotW); hit.setAttribute("height", ROW_H);
    hit.setAttribute("fill", "transparent");
    hit.addEventListener("mousemove", (ev) => showTipHTML(ev, rowTooltip(r)));
    hit.addEventListener("mouseleave", hideTip);
    g.appendChild(hit);

    growBarW(clipRect, totalW);
  });
  summarySvg.appendChild(g);

  // 분기 기준선 — 각 분기가 속한 3개월 행 구간에서만 그려지는 끊어진 세로 점선
  refLines.forEach(rl => {
    const x = PL + (rl.value / maxX) * plotW;
    const rowStart = (rl.q - 1) * 3;
    const line = document.createElementNS(ns, "line");
    line.setAttribute("x1", x); line.setAttribute("x2", x);
    line.setAttribute("y1", PT + rowStart * ROW_H); line.setAttribute("y2", PT + (rowStart + 3) * ROW_H);
    line.setAttribute("stroke", rl.color); line.setAttribute("stroke-width", "1.2");
    line.setAttribute("stroke-opacity", rl.opacity);
    line.setAttribute("stroke-dasharray", "3 2");
    summarySvg.appendChild(line);
  });

  // 범례 — 좁은 칼럼이라 SVG 안에 텍스트로 겹쳐 쓰지 않고 별도 표기
  const legendWrap = document.getElementById("summaryLegend");
  legendWrap.innerHTML = refLines.map(rl =>
    `<span style="opacity:${rl.opacity}"><i class="swatch" style="background:${rl.color}"></i>${rl.year} ${rl.q}분기 월평균 ${rl.value.toFixed(1)}</span>`
  ).join("") || '<span class="empty-inline">비교할 과거 분기 데이터 없음</span>';
}

function renderSummaryTables() {
  const dates = yearDates(currentYear);
  const sums = {}; DATA.categories.forEach(c => sums[c.key] = 0);
  const overLimit = [];
  dates.forEach(ds => {
    const rec = byDateRec[ds];
    if (!rec) return;
    DATA.categories.forEach(c => { sums[c.key] += rec.by_cat[c.key] || 0; });
    const deployCount = rec.by_cat.code_main || 0;
    if (deployCount > VERCEL_LIMIT) overLimit.push({ date: ds, count: deployCount });
  });
  const total = Object.values(sums).reduce((a, b) => a + b, 0);

  document.getElementById("summaryTableTitle").textContent = `${currentYear}년 요약`;

  const ns = "http://www.w3.org/2000/svg";
  const donut = document.getElementById("donut");
  donut.innerHTML = "";
  const R = 55, CX = 70, CY = 70, STROKE = 20;
  const circumference = 2 * Math.PI * R;
  if (total === 0) {
    const bg = document.createElementNS(ns, "circle");
    bg.setAttribute("cx", CX); bg.setAttribute("cy", CY); bg.setAttribute("r", R);
    bg.setAttribute("fill", "none"); bg.setAttribute("stroke", "#2a2c33"); bg.setAttribute("stroke-width", STROKE);
    donut.appendChild(bg);
  } else {
    let offset = 0;
    DATA.categories.forEach(c => {
      const v = sums[c.key];
      if (v <= 0) return;
      const len = (v / total) * circumference;
      const seg = document.createElementNS(ns, "circle");
      seg.setAttribute("cx", CX); seg.setAttribute("cy", CY); seg.setAttribute("r", R);
      seg.setAttribute("fill", "none");
      seg.setAttribute("stroke", c.color);
      seg.setAttribute("stroke-width", STROKE);
      seg.setAttribute("stroke-dasharray", `${len} ${circumference - len}`);
      seg.setAttribute("stroke-dashoffset", String(-offset));
      seg.setAttribute("transform", `rotate(-90 ${CX} ${CY})`);
      seg.style.cursor = "pointer";
      seg.addEventListener("mousemove", (ev) => showTipHTML(ev,
        `<div class="t-row"><span><i class="swatch" style="background:${c.color}"></i>${c.label}</span><b>${v}건</b></div>`));
      seg.addEventListener("mouseleave", hideTip);
      donut.appendChild(seg);
      offset += len;
    });
  }
  document.getElementById("donutTotal").innerHTML = `<b>${total}</b>총 건수`;

  const catRows = DATA.categories
    .map(c => ({ c, v: sums[c.key] }))
    .filter(x => x.v > 0)
    .sort((a, b) => b.v - a.v)
    .map(({ c, v }) => `<tr><td><i class="swatch" style="background:${c.color}"></i>${c.label}</td><td class="num">${v}</td></tr>`)
    .join("");
  document.getElementById("catSummaryTable").innerHTML =
    `<thead><tr><th>항목</th><th class="num">건수</th></tr></thead><tbody>${catRows || '<tr><td colspan="2">데이터 없음</td></tr>'}</tbody>`;

  const overRows = overLimit.map(o => `<tr><td>${o.date}</td><td class="num">${o.count}</td></tr>`).join("");
  document.getElementById("overLimitTable").innerHTML =
    `<thead><tr><th>날짜</th><th class="num">배포 건수</th></tr></thead><tbody>${overRows || '<tr><td colspan="2">초과일 없음</td></tr>'}</tbody>`;
}

renderDetail();
updateRightPanels();
</script>
</body>
</html>
"""


def render_html(data: dict) -> str:
    return _TEMPLATE.replace("__DATA_JSON__", json.dumps(data, ensure_ascii=False))


# ── 네트워크 I/O ────────────────────────────────────────────────────────
def fetch_commits(
    token: str, repo: str, branch: str, since_iso: str,
    *, session: "requests.Session | None" = None, per_page: int = 100,
) -> list[dict]:
    """GitHub REST API 로 커밋 이력 조회. [{"branch","sha","date","message"}, ...]."""
    session = session or requests.Session()
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}
    out: list[dict] = []
    page = 1
    while True:
        resp = session.get(
            f"https://api.github.com/repos/{repo}/commits",
            headers=headers,
            params={"sha": branch, "since": since_iso, "per_page": per_page, "page": page},
            timeout=20,
        )
        resp.raise_for_status()
        items = resp.json()
        if not items:
            break
        for it in items:
            commit = it.get("commit", {}) or {}
            author = commit.get("author", {}) or {}
            msg = (commit.get("message") or "").split("\n", 1)[0]
            out.append({"branch": branch, "sha": it.get("sha"), "date": author.get("date"), "message": msg})
        if len(items) < per_page:
            break
        page += 1
    return out


def run(cfg, *, days: int = 3) -> dict:
    """data+main 브랜치 최근 커밋만 조회해 대시보드를 렌더링하고 devpapers 에 커밋.

    매번 커밋 원본을 넓게 재조회하지 않는다 — `days`(기본 3일, 스케줄러 1시간 주기 대비
    안전 여유분)만큼만 GitHub API 로 가져와 그날 집계를 내고, 그 수치만
    `docs/push_monitor_history.json` 에 누적 병합해 장기 이력(분기 비교 등)을 쌓는다.
    10분 단위 상세(detail/events)는 이 최근 창(window) 안에서만 유지한다.
    """
    from .gh_store import ConflictError, GitHubStore

    now_kst = datetime.now(KST)
    since = (now_kst - timedelta(days=days)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    session = requests.Session()
    records: list[dict] = []
    for branch in ("data", "main"):
        try:
            records.extend(fetch_commits(cfg.github_token, cfg.github_repo, branch, since, session=session))
        except requests.RequestException as e:
            logger.warning("push_monitor: %s 브랜치 조회 실패 — %s", branch, e)

    recent = build_dashboard_data(records, now_kst=now_kst, days=days)

    gh = GitHubStore(cfg.github_token, cfg.github_repo, "devpapers", session=session)
    history: dict = {}
    for attempt in range(2):
        raw_history, hist_sha = gh.read_json(_HISTORY_PATH)
        history = merge_history(raw_history or {}, recent["days"])
        try:
            gh.write_json(
                _HISTORY_PATH, history, prev_sha=hist_sha,
                message=f"docs: push monitor history {now_kst.isoformat()}",
            )
            break
        except ConflictError:
            if attempt == 1:
                raise

    data = dict(recent)
    data["days"] = history_to_days_list(history)
    html = render_html(data)

    # HTML 은 JSON 이 아니므로 Contents API 직접 사용(gh_store 의 write_json 은 JSON 전용).
    changed, _ = gh.write_text("docs/PUSH_MONITOR.html", html, message=f"docs: push monitor {now_kst.isoformat()}")
    return {"records": len(records), "days": days, "changed": changed}


if __name__ == "__main__":
    import sys

    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    print("=" * 70)
    print("push_monitor.py 스모크 테스트")
    print("=" * 70)

    # ── categorize ──
    assert categorize("data", "data: preview 2026-09-13T14:36:05Z") == "preview"
    assert categorize("data", "data: tweet added arale") == "tweet"
    assert categorize("data", "data: notice added x") == "notice"
    assert categorize("data", "data: undo snapshot (...)") == "undo_snapshot"
    assert categorize("data", "data: personal schedule ritsu") == "personal_schedule"
    assert categorize("data", "data: xrelay scheduled ...") == "xrelay"
    assert categorize("data", "data: manual add nonoka broadcast (...)") == "manual"
    assert categorize("data", "data: 기존 preview 4건 제목 번역(title_ko) 소급 반영") == "manual"
    assert categorize("data", "data: 뭔가 새로운 패턴") == "other_data"
    assert categorize("main", "fix(v3.2.2): ...") == "code_main"
    print("[OK] categorize: 9개 카테고리 분류")

    # ── build_dashboard_data ──
    now = datetime(2026, 9, 14, 10, 0, 0, tzinfo=KST)
    recs = [
        {"branch": "data", "date": "2026-09-13T14:36:05Z", "message": "data: preview 2026-09-13T14:36:05Z"},
        {"branch": "data", "date": "2026-09-13T14:34:05Z", "message": "data: preview 2026-09-13T14:34:05Z"},
        {"branch": "data", "date": "2026-09-13T05:00:00Z", "message": "data: tweet added arale"},
        {"branch": "main", "date": "2026-09-13T13:00:00Z", "message": "fix: x"},
        {"branch": "data", "date": "2026-09-10T00:00:00Z", "message": "data: preview old"},  # lookback 밖(2일치만 테스트)
    ]
    d = build_dashboard_data(recs, now_kst=now, days=2)
    assert [x["date"] for x in d["days"]] == ["2026-09-13", "2026-09-14"], d["days"]
    day13 = d["days"][0]
    assert day13["total"] == 4, day13
    assert day13["by_cat"]["preview"] == 2 and day13["by_cat"]["tweet"] == 1 and day13["by_cat"]["code_main"] == 1
    assert len(d["detail"]["2026-09-13"]) == 144
    # UTC 14:34/14:36 → KST 23:34/23:36, 둘 다 10분 bin 141(23:30~23:40)에 들어감
    bin_141 = d["detail"]["2026-09-13"][141]
    assert bin_141["preview"] == 2, bin_141
    print("[OK] build_dashboard_data: 날짜·카테고리·10분 bin 집계")

    evs_141 = [e for e in d["events"]["2026-09-13"] if e["bin"] == 141]
    assert len(evs_141) == 2 and all(e["cat"] == "preview" for e in evs_141), evs_141
    assert evs_141 == sorted(evs_141, key=lambda e: e["time"]), evs_141
    print("[OK] build_dashboard_data: bin별 개별 이벤트(events) 시간순 기록")

    # 2026-09-10 은 lookback(2일) 밖이라 반영 안 됨
    assert all("2026-09-10" != x["date"] for x in d["days"])
    print("[OK] build_dashboard_data: lookback 밖 날짜 제외")

    # ── render_html ──
    html = render_html(d)
    assert "<title>Push Monitor</title>" in html
    assert "__DATA_JSON__" not in html
    assert '"2026-09-13"' in html
    print("[OK] render_html: 템플릿에 데이터 임베드, 플레이스홀더 치환 완료")

    # ── merge_history / history_to_days_list ──
    hist = merge_history({}, d["days"])
    assert set(hist) == {"2026-09-13", "2026-09-14"}, hist
    assert hist["2026-09-13"]["preview"] == 2
    # 기존 이력에 없던 옛날 날짜는 유지, 겹치는 날짜만 최신 값으로 덮어씀
    hist2 = merge_history({"2026-01-01": {"code_main": 5}, "2026-09-13": {"code_main": 999}}, d["days"])
    assert hist2["2026-01-01"] == {"code_main": 5}
    assert hist2["2026-09-13"]["code_main"] == 1  # 최근 재조회 값으로 덮어씀(999 아님)
    dl = history_to_days_list(hist2)
    assert [x["date"] for x in dl] == ["2026-01-01", "2026-09-13", "2026-09-14"]  # 날짜 오름차순
    assert dl[0]["total"] == 5
    print("[OK] merge_history/history_to_days_list: 장기 이력 누적 병합(수치만, 원본 아님)")

    print("\nSUCCESS: push_monitor.py self-test 통과 (mock)")

    if "--live" in sys.argv:
        import os
        key = os.environ.get("GITHUB_FINEGRAINED_PAT") or os.environ.get("GITHUB_TOKEN")
        repo = os.environ.get("GITHUB_REPO", "sbb2002/mewtype-scheduler")
        if not key:
            print("\n[skip] --live 이지만 GITHUB_TOKEN 없음")
        else:
            print("\n실호출: fetch_commits(data, 최근 1일) ...")
            recs_live = fetch_commits(key, repo, "data", (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ"))
            print(f"  {len(recs_live)}건 조회됨")
