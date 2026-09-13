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
    "code_main": "#222222",
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

    def ensure_day(d: str) -> None:
        if d not in day_totals:
            day_totals[d] = {c: 0 for c in CATEGORY_ORDER}
            detail[d] = [{c: 0 for c in CATEGORY_ORDER} for _ in range(_BINS_PER_DAY)]

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

    days_list = []
    for i in range(days):
        d = (start_date + timedelta(days=i)).isoformat()
        ensure_day(d)
        days_list.append({
            "date": d,
            "total": sum(day_totals[d].values()),
            "by_cat": day_totals[d],
        })

    return {
        "generated_at": now_kst.strftime("%Y-%m-%dT%H:%M:%S+09:00"),
        "days": days_list,
        "detail": detail,
        "categories": [
            {"key": c, "label": CATEGORY_LABELS[c], "color": CATEGORY_COLORS[c]}
            for c in CATEGORY_ORDER
        ],
    }


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
       padding:24px 20px 60px;max-width:1100px;margin:0 auto}
  h1{font-size:1.3rem;margin:0 0 4px}
  .sub{color:var(--muted);font-size:.85rem;margin:0 0 22px}
  .panel{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:20px}
  .legend{display:flex;flex-wrap:wrap;gap:10px 16px;font-size:.78rem;color:var(--muted);margin-bottom:14px}
  .legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
  .heat{display:flex;flex-wrap:wrap;gap:4px}
  .heat .cell{width:28px;height:28px;border-radius:4px;cursor:pointer;border:1px solid transparent;flex:none}
  .heat .cell.sel{border-color:var(--accent)}
  .heat .cell:hover{border-color:#fff}
  .heat-axis{display:flex;justify-content:space-between;color:var(--muted);font-size:.72rem;margin-top:6px}
  .detail-title{font-size:1rem;margin:0 0 2px}
  .detail-sub{color:var(--muted);font-size:.8rem;margin:0 0 14px}
  .chart-wrap{position:relative;overflow-x:auto}
  svg{display:block}
  .bar{cursor:pointer}
  .xaxis text{fill:var(--muted);font-size:9px}
  .tooltip{position:fixed;background:#1c1e24;border:1px solid var(--line);border-radius:8px;
           padding:8px 10px;font-size:.76rem;pointer-events:none;z-index:50;display:none;
           box-shadow:0 6px 20px rgba(0,0,0,.4);max-width:260px}
  .tooltip .t-time{color:var(--muted);margin-bottom:4px}
  .tooltip .t-row{display:flex;justify-content:space-between;gap:14px}
  .tooltip .t-row b{color:var(--ink)}
  .empty{color:var(--muted);text-align:center;padding:30px 0}
  footer{color:var(--muted);font-size:.75rem;margin-top:30px;text-align:center}
</style>
</head>
<body>
<h1>Push Monitor</h1>
<p class="sub">data/main 브랜치 커밋(=Vercel 배포 시도) 활동 — Hobby 플랜 하루 100건 한도 재소진 조기 감지용.
날짜 칸을 클릭하면 그 날의 10분 단위 상세를 아래에서 봅니다.</p>

<div class="panel">
  <div class="legend" id="legend"></div>
  <div class="heat" id="heat"></div>
  <div class="heat-axis"><span id="heatFrom"></span><span id="heatTo"></span></div>
</div>

<div class="panel">
  <h2 class="detail-title" id="detailTitle">—</h2>
  <p class="detail-sub" id="detailSub"></p>
  <div class="chart-wrap"><svg id="chart" width="1040" height="320"></svg></div>
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

// ── 히트맵 ──
const heat = document.getElementById("heat");
const maxTotal = Math.max(1, ...DATA.days.map(d => d.total));
function heatColor(total) {
  if (total === 0) return "#1c1e24";
  const t = Math.min(1, total / maxTotal);
  // 단일 색상(teal) 명도만 증가 — 값이 클수록 밝게, GitHub 잔디 스타일.
  const light = 18 + t * 42; // 18% ~ 60%
  return `hsl(175, 55%, ${light}%)`;
}
let selectedDate = DATA.days.length ? DATA.days[DATA.days.length - 1].date : null;

function buildHeat() {
  heat.innerHTML = "";
  DATA.days.forEach(d => {
    const cell = document.createElement("div");
    cell.className = "cell" + (d.date === selectedDate ? " sel" : "");
    cell.style.background = heatColor(d.total);
    cell.title = `${d.date}: ${d.total}건`;
    cell.addEventListener("click", () => { selectedDate = d.date; buildHeat(); renderDetail(); });
    heat.appendChild(cell);
  });
}
if (DATA.days.length) {
  document.getElementById("heatFrom").textContent = DATA.days[0].date;
  document.getElementById("heatTo").textContent = DATA.days[DATA.days.length - 1].date;
}
buildHeat();

// ── 상세 차트 ──
const svg = document.getElementById("chart");
const tooltip = document.getElementById("tooltip");
const W = 1040, H = 320, PAD_L = 40, PAD_B = 30, PAD_T = 10;
const plotW = W - PAD_L - 10, plotH = H - PAD_T - PAD_B;

function renderDetail() {
  const day = DATA.days.find(d => d.date === selectedDate);
  const bins = DATA.detail[selectedDate] || [];
  document.getElementById("detailTitle").textContent = selectedDate || "—";
  document.getElementById("detailSub").textContent = day ? `총 ${day.total}건` : "데이터 없음";
  svg.innerHTML = "";
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
      rect.setAttribute("y", PAD_T + plotH - (y0 + h));
      rect.setAttribute("width", Math.max(barW - 0.4, 0.6));
      rect.setAttribute("height", h);
      rect.setAttribute("fill", c.color);
      rect.classList.add("bar");
      rect.addEventListener("mousemove", (ev) => showTip(ev, i, b, totals[i]));
      rect.addEventListener("mouseleave", hideTip);
      g.appendChild(rect);
      y0 += h;
    });
    // 빈 bin 도 호버 가능하게 투명 히트 영역
    if (totals[i] === 0) {
      const hit = document.createElementNS(ns, "rect");
      hit.setAttribute("x", PAD_L + i * barW);
      hit.setAttribute("y", PAD_T);
      hit.setAttribute("width", Math.max(barW - 0.4, 0.6));
      hit.setAttribute("height", plotH);
      hit.setAttribute("fill", "transparent");
      hit.addEventListener("mousemove", (ev) => showTip(ev, i, b, 0));
      hit.addEventListener("mouseleave", hideTip);
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

function showTip(ev, binIdx, bin, total) {
  const hh = String(Math.floor(binIdx / 6)).padStart(2, "0");
  const mm = String((binIdx % 6) * 10).padStart(2, "0");
  let rows = "";
  DATA.categories.forEach(c => {
    const v = bin[c.key] || 0;
    if (v > 0) rows += `<div class="t-row"><span>${c.label}</span><b>${v}</b></div>`;
  });
  tooltip.innerHTML = `<div class="t-time">${selectedDate} ${hh}:${mm} (총 ${total}건)</div>` +
    (rows || '<div class="t-row"><span>변화 없음</span></div>');
  tooltip.style.display = "block";
  tooltip.style.left = (ev.clientX + 14) + "px";
  tooltip.style.top = (ev.clientY + 14) + "px";
}
function hideTip() { tooltip.style.display = "none"; }

renderDetail();
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


def run(cfg, *, days: int = 7) -> dict:
    """data+main 브랜치 커밋 이력을 모아 대시보드를 렌더링하고 devpapers 에 커밋."""
    from .gh_store import GitHubStore

    now_kst = datetime.now(KST)
    since = (now_kst - timedelta(days=days)).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    session = requests.Session()
    records: list[dict] = []
    for branch in ("data", "main"):
        try:
            records.extend(fetch_commits(cfg.github_token, cfg.github_repo, branch, since, session=session))
        except requests.RequestException as e:
            logger.warning("push_monitor: %s 브랜치 조회 실패 — %s", branch, e)

    data = build_dashboard_data(records, now_kst=now_kst, days=days)
    html = render_html(data)

    gh = GitHubStore(cfg.github_token, cfg.github_repo, "devpapers")
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

    # 2026-09-10 은 lookback(2일) 밖이라 반영 안 됨
    assert all("2026-09-10" != x["date"] for x in d["days"])
    print("[OK] build_dashboard_data: lookback 밖 날짜 제외")

    # ── render_html ──
    html = render_html(d)
    assert "<title>Push Monitor</title>" in html
    assert "__DATA_JSON__" not in html
    assert '"2026-09-13"' in html
    print("[OK] render_html: 템플릿에 데이터 임베드, 플레이스홀더 치환 완료")

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
