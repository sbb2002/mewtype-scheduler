"""trace.json + results.json + v4a_flow.html(스타일 · 엔진) → ref/v4a/v4a_verify_flow.html

각 "동작"(업스트림 알림 1건 · reconcile 1회 · 관리 페이지 조작 1건 …)을 흐름도의 기능 칩 하나로 만들고,
그 동작 동안 실제로 관측된 단계를 흐름도 경로 도우미(X_IN · CQ · QB · viaBe …)로 옮겨 재생한다.
흐름도(설계)와 다른 단계는 흰 테두리(n) + 사유.
"""
import html as H
import json
import re
import subprocess
from collections import OrderedDict
from pathlib import Path

HERE = Path(__file__).resolve().parent
V4A = HERE.parents[2]           # 저장소 루트
SRC = V4A / "ref/v4a/v4a_flow.html"
OUT = V4A / "ref/v4a/v4a_verify_flow.html"

T = json.loads((HERE / "trace.json").read_text(encoding="utf-8"))
R = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
src = SRC.read_text(encoding="utf-8")
commit = subprocess.run(["git", "-C", str(V4A), "log", "-1", "--format=%h"], capture_output=True, text=True).stdout.strip()

WAITED_OK = {"reconcile", "yt_notif", "snapshot"}          # 결과를 기다리지 않는 적재(나머지는 로컬 한정 대기)
ACT = {"intake": "ctrl", "writer": "be", "enrich": "ctrl"}

# ── 동작 단위로 자르기 ────────────────────────────────────────────────────────
actions, cur = [], None
for e in T:
    if e["step"] == "action":
        cur = {"scenario": e["scenario"], "label": e["label"], "trigger": e.get("trigger"), "events": [], "checks": []}
        actions.append(cur)
        continue
    if cur is None or e["scenario"] != cur["scenario"]:
        continue
    if e["step"] == "check":
        cur["checks"].append(e)
    else:
        cur["events"].append(e)

RES_BY_SC = OrderedDict()
for r in R:
    RES_BY_SC.setdefault(r["scenario"], []).append(r)


def _kst(iso):
    from datetime import datetime, timedelta
    return (datetime.fromisoformat(iso.replace("Z", "+00:00")) + timedelta(hours=9)).strftime("%H:%M")


def js(s):
    return json.dumps(s, ensure_ascii=False)


def step_of(e, a, first_enqueue_done):
    """관측 이벤트 → (종류, 경로 JS, 설명, 흐름도와 다른 점 사유 | None, stop)."""
    st, who = e["step"], ACT.get(e["actor"], "ctrl")
    th = e["thread"].replace("MainThread", "접수(요청 스레드)")
    if st == "http-in":
        p = e["path"]
        if p == "/ingest":
            return ("E", "X_IN", "업스트림 알림 → 접수 /ingest", None, False)
        if p == "/telegram":
            return ("E", "CMD", "텔레그램 명령 → 접수 /telegram (로컬: getUpdates 폴링이 전달)", None, False)
        if p.startswith("/admin/api/") and e["method"] == "POST":
            return ("E", "ADM", f"관리 페이지 → POST {p.replace('/admin/api', '')} (세션 + CSRF)", None, False)
        if p.startswith("/admin"):
            return ("E", "ADM", f"관리 페이지 → GET {p}", None, False)
        if p.startswith("/monitor-live"):
            return ("F", "WEB", "브라우저 → 웹 모니터 /monitor-live", None, False)
        if p.startswith("/data") or p == "/":
            return ("F", '["browser","cdn"]', f"브라우저 → 로컬 러너 {p}", None, False)
        return None
    if st == "external":
        svc = {"youtube": "yt", "groq": "groq", "vxtwitter": "vx", "yt-dlp": "ytdlp"}[e["svc"]]
        route = f'rt(viaCtrl("{svc}"))' if who == "ctrl" else f'rt(viaBe("{svc}"))'
        why = "D4 결정 — 시작+2분 search.list 1회 (흐름도에 없는 조회)" if "search.list" in e["call"] else None
        return ("X", route, f"{e['svc']} · {e['call']} [{th}]", why, False)
    if st == "enqueue":
        kind = e["kind"] + (f"({e.get('scope')})" if e.get("scope") else "")
        sched = (" · 예약 " + _kst(e["run_at"]) + " KST") if e.get("run_at") and e.get("name") else ""
        if e["queue"] == "enrich":
            return ("O", "BQE", f"가공 큐에 {kind} 적재{sched} [{th}]", None, False)
        if a["trigger"] == "schedule" and e["kind"] in ("reconcile", "snapshot") and not first_enqueue_done:
            return ("E", "SCHQ", f"정기 잡 → 적용 큐에 {kind} 적재",
                    "로컬: 스케줄러 스레드가 적용 큐에 적재 (흐름도: Scheduler → 쓰기 서비스 직접). 같은 한 줄에 선다는 점은 같음",
                    False)
        if who == "be":
            return ("O", "BQ", f"다음 확인 적재 {kind}{sched} [q-apply]", None, False)
        why = None
        if e["kind"] == "yt_notif":
            why = "D1~D3 결정 — 알림을 상태 신호로 쓰는 yt_notif 작업 (흐름도 #12 는 reconcile(영상)만)"
        elif e["kind"] not in WAITED_OK:
            why = "로컬 한정 — 적재 후 결과를 기다린다 (흐름도: 적재하고 바로 응답). 계획 §1 알려진 차이"
        return ("O", "CQ", f"적용 큐에 {kind} 적재{sched} [{th}]", why, False)
    if st == "job-start":
        if e["queue"] == "enrich":
            return ("O", "QEC", f"가공 큐 → {e['kind']} 실행 (q-enrich = 흐름도 /enrich)", None, False)
        why = ("D1~D3 결정 — yt_notif: reconcile(영상) 후 tunein→watching · 시작→live" if e["kind"] == "yt_notif" else None)
        return ("O", "QB", f"쓰기 스레드 q-apply 가 {e['kind']}" + (f"({e.get('scope')})" if e.get("scope") else "")
                + " 실행" + (f" (시도 {e['attempt']})" if (e.get("attempt") or 1) > 1 else ""), why, False)
    if st == "job-fail":
        return ("O", '["be"]', f"{e['kind']} 실패 — {e.get('error', '')}", None, True)
    if st == "write":
        b, p = e["branch"], e["path"]
        node = {"data": "data", "ops": "ops", "monitoring": "mon", "raw": "raw"}.get(b, b)
        route = "RAWP" if node == "raw" else js([who, node])
        why = None
        if node == "raw":
            why = "D19 결정 — 스케줄 관련 원문 보존 (흐름도에 없는 저장소, 로컬 전용)"
        elif node == "ops" and p == "history.json":
            why = "작업 이력을 접수 쪽(admin_api)이 기록 (흐름도: 쓰기 서비스가 작업 결과와 함께)"
        elif node == "ops" and p == "admin_state.json" and who == "be":
            why = "v3 undo 슬롯 · 편집 락 잔재를 쓰기 스레드가 계속 기록 (흐름도: 작업 이력으로 대체)"
        elif node == "ops" and p == "admin_state.json" and who == "ctrl":
            why = "재등록 차단(suppress)을 접수 쪽이 기록 (흐름도: 쓰기 서비스)"
        lab = {"monitoring/events": "이벤트 로그 한 줄", "monitoring/lost_queue.json": "유실 원문 큐"}
        desc = next((v for k, v in lab.items() if p.startswith(k)), p)
        return ("S", route, f"쓰기 _local/{b}/{desc} [{th}]", why, False)
    if st == "dm":
        why = None
        if who == "ctrl" and a["trigger"] == "upstream":
            why = "로컬 한정 — 결과 DM 을 접수 쪽이 보냄 (흐름도 #7: 쓰기 서비스가 커밋 뒤)"
        return ("X", "BE_DM" if who == "be" else "DM", "DM: " + re.sub(r"\s+", " ", e["text"])[:46], why, False)
    if st == "VIOLATION":
        return ("O", js([who]), "위반: " + e["what"], "원칙 위반", True)
    return None


groups = OrderedDict()
F_js, rows = [], []
for a in actions:
    sc = a["scenario"]
    if sc not in groups:
        groups[sc] = chr(ord("A") + len(groups))
    g = groups[sc]
    steps, prev, whys, outs, first_enq = [], None, [], [], False
    for e in a["events"]:
        r = step_of(e, a, first_enq)
        if r is None:
            continue
        if r[1] == "SCHQ":
            first_enq = True
        key = (r[0], r[1], r[2])
        if key == prev:
            continue
        prev = key
        steps.append(r)
        if r[3] and r[3] not in whys:
            whys.append(r[3])
        if e["step"] == "write" and e["branch"] == "data" and e["path"] not in outs:
            outs.append(e["path"])
    if not steps:
        continue
    n = sum(1 for x in F_js if x[0] == g) + 1
    fid = f"{g}{n}"
    checks = [("✓ " if c["ok"] else "✗ ") + f"[{c['feature']}] {c['desc']}" for c in a["checks"]]
    c = "차이" if whys else "일치"
    trig = {"upstream": "업스트림(폰 Automate)", "schedule": "정기 잡 / 예약 시각 도달", "admin": "관리 페이지",
            "telegram": "텔레그램 비상 명령"}.get(a["trigger"], a["trigger"] or "")
    st_js = ",\n        ".join(
        f's({js(k)},[{route}],{js(t)}{",{n:true}" if w else ""}{",{stop:true}" if stop else ""})'
        for k, route, t, w, stop in steps)
    obj = (f'{{id:{js(fid)}, g:{js(g)}, t:{js(a["label"])}, c:{js(c)}, trig:{js(trig)}, '
           f'out:{js(", ".join(outs) or "—")}, why:{js(" / ".join(whys))}, checks:{js(checks)},\n      steps:[\n        {st_js}\n      ]}}')
    F_js.append((g, obj))

F_src = "var F = [\n    " + ",\n    ".join(o for _, o in F_js) + "\n  ];"
G_src = "var G = " + js(OrderedDict((v, k) for k, v in groups.items())) + ";"

# ── 노드 (로컬 대응물) ─────────────────────────────────────────────────────────
N_src = '''var N = {
    push:   [20,122,160,42,"X·YouTube 푸시","서드파티 알림","ext"],
    up:     [20,206,160,44,"업스트림 · Automate","폰 → Tailscale → /ingest"],
    op:     [20,318,160,42,"운영자","텔레그램 알림 · 비상 명령"],
    adm:    [20,476,160,44,"관리 페이지",["운영자 브라우저","/admin (Tailscale IP)"],"new"],
    tg:     [20,410,160,44,"Telegram Bot API","로컬 봇 · getUpdates 폴링","ext"],
    sch:    [20,548,160,46,"정기 잡 (로컬)",["scheduler 스레드","10분 · 06:00 · 06:10"]],
    ctrl:   [290,222,190,66,"접수 서비스",["로컬: Flask 접수 앱","/ingest · /telegram · /admin"]],
    qa:     [300,352,170,54,"적용 큐",["로컬: LocalQueue(apply)","순차 1 · 예약 · 재시도"]],
    be:     [290,470,190,66,"쓰기 서비스",["로컬: 스레드 q-apply","data 를 쓰는 유일한 스레드"]],
    qe:     [290,618,190,50,"가공 큐",["로컬: LocalQueue(enrich)","스레드 q-enrich · 번역 수집"],"new"],
    data:   [620,200,180,62,"_local/data",["preview · notices · tweets","q-apply 만 씀"]],
    ops:    [620,330,180,62,"_local/ops",["control · admin_state","작업 이력 · 로그인 nonce"],"new"],
    mon:    [620,466,180,62,"_local/monitoring",["이벤트 로그 · 스냅샷","유실 큐"]],
    raw:    [620,576,180,50,"_local/raw",["스케줄 원문 보존 (D19)","로컬 전용"],"new"],
    cdn:    [870,200,160,62,"/data/* 서빙",["로컬 러너 · no-store","(raw CDN 대신)"]],
    browser:[870,330,160,58,"브라우저","index · monitor · admin"],
    yt:     [300,34,140,46,"YouTube","RSS · Data API","ext"],
    ytdlp:  [455,34,140,46,"yt-dlp","채널 streams 탭","ext"],
    groq:   [610,34,140,46,"Groq LLM","번역 · 판정","ext"],
    vx:     [765,34,140,46,"vxtwitter / fxtwitter","트윗 원문 복원","ext"]
  };'''

script = re.findall(r"<script>(.*?)</script>", src, flags=re.S)[0]
script = re.sub(r"var N = \{.*?\n  \};", lambda m: N_src, script, count=1, flags=re.S)
script = re.sub(r"var G = \{.*?\n  \};", lambda m: G_src, script, count=1, flags=re.S)
script = re.sub(r"var F = \[.*?\n  \];", lambda m: F_src, script, count=1, flags=re.S)
# 로컬 추가 경로: 정기 잡 → 적용 큐, 접수 → 원문 보존
script = script.replace('  var MON_ADM', '  var SCHQ = ["sch",[250,571],[250,379],"qa"];\n'
                        '  var RAWP = ["ctrl",[552,262],[552,601],"raw"];\n  var MON_ADM', 1)
script = script.replace('<span class="c">v3.8.10 대비 ', '<span class="c">흐름도 대조 ')
script = script.replace('<span class="v4">v4a</span>', '<span class="v4">차이</span>')
script = script.replace('f.c !== "유지"', 'f.c !== "일치"')
script = script.replace("v3.8.10에서 바뀐 단계", "흐름도(설계)와 다른 단계")
script = script.replace("'<div class=\"chgbox\">v3.8.10에서 바뀐 점 — '", "'<div class=\"chgbox\">흐름도와 다른 점 — '")
script = script.replace("    capEl.innerHTML = h;",
                        "    if (f.checks && f.checks.length) h += '<ul class=\"checks\">' + f.checks.map(function(c){"
                        " return '<li class=\"' + (c[0] === \"✓\" ? \"ok\" : \"ng\") + '\">' + esc(c) + '</li>'; }).join('') + '</ul>';\n"
                        "    capEl.innerHTML = h;", 1)
assert "SCHQ" in script and "RAWP" in script and "checks" in script

style = re.findall(r"<style>(.*?)</style>", src, flags=re.S)[0]
style += """
  .checks{list-style:none;margin:10px 0 0;padding:0;font-size:12.5px}
  .checks li{padding:3px 0 3px 2px;color:var(--dim)}
  .checks li.ok{color:#8fe3ae} .checks li.ng{color:var(--warn)}
  .verdict{display:inline-block;padding:2px 8px;border-radius:6px;font-size:12px;font-weight:600}
  .verdict.ok{background:#1f3a2a;color:#8fe3ae} .verdict.ng{background:#3a1f1f;color:#ff8a7a}
  .kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:10px;margin:18px 0 8px}
  .kpi div{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
  .kpi b{display:block;font-size:22px;color:var(--ink);font-family:var(--f-mono)}
  .kpi span{font-size:12.5px;color:var(--dim)}
"""
head = src[: src.index("<style>")]
head = re.sub(r"<title>.*?</title>", "<title>v4a 검증 흐름</title>", head)

# ── 본문 ─────────────────────────────────────────────────────────────────────
ok_n = sum(r["ok"] for r in R)
prin = [r for r in R if r["feature"].startswith("원칙")]
diff_actions = sum(1 for _, o in F_js if 'c:"차이"' in o)
DIFFS = [
    ("로컬 한정", "접수 쪽이 적용 큐 결과를 기다린다", "흐름도 원칙 ②는 적재 후 바로 응답. 로컬 시험판은 현행 DM 문구를 유지하려고 "
     "<code>submit_and_wait</code> 로 기다린다. Cloud Tasks 는 결과를 돌려주지 않으므로 배포 단계에서 비동기 적재 + 작업 결과 조회로 바꿔야 한다."),
    ("로컬 한정", "업스트림 알림의 결과 DM 을 접수 쪽이 보낸다", "흐름도 #7 은 쓰기 서비스가 커밋 뒤 DM. 위와 같은 이유(결과를 기다리므로 기존 코드가 그 자리에서 DM)."),
    ("로컬 한정", "정기 잡이 적용 큐를 거친다", "흐름도는 Scheduler → 쓰기 서비스 <code>/reconcile</code> 직접. 로컬은 스케줄러 스레드가 적용 큐에 "
     "reconcile 을 적재하고 q-apply 가 실행 — '같은 인스턴스에서 작업과 한 줄로 선다'는 설계 의도와 같은 결과."),
    ("결정 반영", "YouTube 알림 → <code>yt_notif</code> 작업", "흐름도 #12 는 reconcile(영상)만. D1~D3 결정으로 reconcile(영상) 후 tunein→watching · "
     "시작→live 를 알림으로 올리고, URL 없는 예고는 ±45분 자리표시에 URL 을 붙인다."),
    ("결정 반영", "시작+2분 <code>search.list</code> · 원문 보존 <code>_local/raw</code>", "D4 · D19 결정으로 생긴 단계 — 흐름도(09-28)에는 없다."),
    ("보완 필요", "작업 이력 · 재등록 차단을 접수 쪽이 기록", "흐름도는 쓰기 서비스가 작업 결과와 함께 ops 에 기록. 로컬은 <code>admin_api</code>(접수)가 "
     "적재 결과를 받은 뒤 ops 에 쓴다. 결과를 기다리는 구조라 지금은 순서가 맞지만, 비동기로 바꾸면 쓰기 쪽으로 옮겨야 한다."),
    ("보완 필요", "v3 undo 슬롯 · 편집 락 잔재", "merge_rows 등 v3 커밋 함수가 여전히 <code>admin_state.json</code> 의 undo 슬롯 · 편집 락을 쓴다(ops 로 라우팅됨). "
     "흐름도는 항목 단위 되돌리기(작업 이력)로 대체 — 이번 범위 밖(되돌리기 미구현)."),
    ("미검증", "#24 생존 신호 · #17 healthchecks/Vercel 조회 · #26 배포 · #10 비전 OCR", "로컬 시험판 설정에 healthchecks · Vercel 이 없고 배포는 하지 않는다. "
     "OCR 은 대상 이미지 소식을 재생하지 않았다."),
]
diff_rows = "\n".join(
    f'<tr><td><span class="c{" chg" if k != "로컬 한정" else ""}">{H.escape(k)}</span></td><td><b>{t}</b></td><td>{d}</td></tr>'
    for k, t, d in DIFFS)
res_rows = []
for sc, rs in RES_BY_SC.items():
    for r in rs:
        res_rows.append(f'<tr><td>{H.escape(sc)}</td><td><code>{H.escape(r["feature"])}</code></td><td>{H.escape(r["check"])}</td>'
                        f'<td><span class="verdict {"ok" if r["ok"] else "ng"}">{"통과" if r["ok"] else "실패"}</span></td></tr>')
FIXED = [
    ("유실 원문 중복 · 엉터리 재투입", "결과를 기다린 작업이 실패하면 접수 · 쓰기 양쪽이 유실 큐에 넣고 DM 도 두 번. 쓰기 쪽 항목은 작업 인자 JSON 이라 재투입하면 트윗 · 소식으로 잘못 등록",
     "33eebe1"),
    ("관리 페이지 로그인 토큰 ↔ 세션 쿠키 혼용", "같은 서명이라 로그인 링크 토큰을 쿠키로 넣으면 nonce 소모 없이 읽기 API 접근 가능 → 용도 구분 서명", "3051213"),
    ("예고 편집이 저장되지 않음", "submitEdit 이 두 번 정의돼 소식용이 예고용을 덮어씀 (브라우저 확인에서 발견)", "4ac110e"),
    ("예고 시각 9시간 밀림", "KST 라벨 칸에 UTC 값을 넣고 저장 때 브라우저 시간대로 해석 — 손대지 않고 저장만 해도 변경", "4ac110e"),
    ("관리 페이지 작업 탭 필드 불일치 · 작업 이력 표 누락", "대기 작업 · 최근 결과가 실제 응답 필드와 달라 비어 보였고, 명세의 작업 이력 표가 없었음", "4ac110e"),
    ("(예방) 운영 봇 토큰으로 로컬 폴링 시 운영 webhook 삭제", "폴링 시작 시 deleteWebhook — webhook 이 걸린 봇이면 폴링 거부", "7ca77e8"),
]
fixed_rows = "\n".join(f"<tr><td><b>{H.escape(a)}</b></td><td>{H.escape(b)}</td><td><code>{c}</code></td></tr>" for a, b, c in FIXED)

body = f'''<body>
<div class="wrap">

  <header class="hero">
    <p class="eyebrow">mewtype-scheduler · v4a 로컬 시험판 검증</p>
    <h1>v4a 검증 흐름 — 흐름도대로 움직였나</h1>
    <p>v4a 로컬 시험판(브랜치 <code>v4a</code>)을 실제 구성 그대로 띄워 — Flask 접수 앱 + 쓰기 스레드 <b>q-apply</b> + 가공 스레드 <b>q-enrich</b> + <code>_local/</code> 저장소 —
      업스트림 알림 · 정기 reconcile · 관리 페이지 조작을 흘리고, <b>관측된 단계를 그대로</b> 흐름도(<code>v4a_flow.html</code>)의 노드 · 경로 위에 재생한다.
      외부 서비스(YouTube Data API · RSS · Groq · vxtwitter · yt-dlp · Telegram 전송)만 가짜로 바꿨다 — 그 밖의 코드 경로는 실제 코드다.</p>
    <p>묶음 탭 = 시나리오, 기능 칩 = 동작 하나(알림 1건 · reconcile 1회 · 관리 조작 1건). <b>흰 테두리 번호</b> = 흐름도(설계)와 다른 단계 — 칩 아래 사유와 그 동작의 확인 결과가 함께 나온다.</p>
    <div class="meta">
      <span>기준 커밋 <b>v4a {H.escape(commit)}</b></span>
      <span>검증 <b>2026-09-29</b></span>
      <span>계획 <b>ref/v4a/v4a_impl_plan.md</b></span>
      <span>결정 <b>ref/v4a/v4a_decisions.md</b></span>
      <span>보고 <b>ref/v4a/v4a_verify_report.md</b></span>
    </div>
  </header>

  <div class="kpi">
    <div><b>{ok_n} / {len(R)}</b><span>확인 통과 (기능 · 결정 · 원칙)</span></div>
    <div><b>{sum(r["ok"] for r in prin)} / {len(prin)}</b><span>원칙 ①③④⑤ — data 쓰기 스레드 · 지름길 · 외부 호출 위치 · ops</span></div>
    <div><b>{len(F_js)}</b><span>재생한 동작 (시나리오 {len(groups)}개)</span></div>
    <div><b>{diff_actions}</b><span>흐름도와 다른 단계가 있는 동작 — 아래 표로 분류</span></div>
  </div>

  <h2>검증 흐름 (관측)</h2>
  <p class="sub">선 색 = 단계 종류. 점선 박스 = 서드파티. 노드 부제 = 로컬 대응물. 원 번호 위치 = 그 단계가 지나간 경로. 저장소 읽기는 기록하지 않았다(쓰기만).</p>
  <div class="legend" id="legend"></div>

  <div class="diagram">
    <div class="tabs" role="tablist" id="tabs"></div>
    <div class="chips" id="chips" aria-label="동작 목록"></div>
    <div class="ctrlbar">
      <button class="btn" id="bPrev" type="button">◀ 이전 동작</button>
      <button class="btn" id="bPlay" type="button">⏸ 일시정지</button>
      <button class="btn" id="bRe" type="button">⟲ 처음부터</button>
      <button class="btn" id="bNext" type="button">다음 동작 ▶</button>
      <span class="now" id="now"></span>
    </div>
    <div class="stage-scroll"><div class="stage">
      <svg id="svg" viewBox="0 0 1240 700" role="img" aria-label="v4a 검증 흐름">
        <rect class="group-b" x="8" y="96" width="184" height="514" rx="10"/>
        <text class="group-t" x="18" y="112">입력 · 트리거</text>
        <rect class="group-b" x="278" y="200" width="226" height="486" rx="10"/>
        <text class="group-t" x="288" y="216">로컬 러너 (한 프로세스)</text>
        <rect class="group-b" x="608" y="178" width="204" height="460" rx="10"/>
        <text class="group-t" x="618" y="194">로컬 저장소 _local/</text>
        <rect class="group-b" x="288" y="12" width="640" height="76" rx="10"/>
        <text class="group-t" x="296" y="26">외부 서비스 (검증에서는 가짜)</text>
        <rect class="group-b" x="858" y="178" width="184" height="226" rx="10"/>
        <text class="group-t" x="868" y="194">프론트 (Tailscale IP)</text>
        <g id="skel"></g>
        <g id="done"></g>
        <g id="routes"></g>
        <g id="nodes"></g>
        <g id="packets"></g>
        <g id="badges"></g>
      </svg>
    </div></div>
    <div class="cap" id="cap"></div>
  </div>

  <h2>흐름도와 다른 점</h2>
  <p class="sub">관측 단계 중 흐름도(설계, 09-28)와 다른 것을 성격별로 묶었다. <b>로컬 한정</b> = 로컬 시험판을 위해 일부러 둔 차이 · <b>결정 반영</b> = 09-29 결정(D1~D25)이 흐름도보다 뒤 · <b>보완 필요</b> = 배포 전에 맞춰야 할 것.</p>
  <div class="tbl-scroll"><table>
    <thead><tr><th>성격</th><th>차이</th><th>설명</th></tr></thead>
    <tbody>{diff_rows}</tbody>
  </table></div>

  <h2>동작 목록</h2>
  <p class="sub">칩과 같은 목록. 번호를 누르면 위 흐름으로 이동한다.</p>
  <div class="tbl-scroll"><table>
    <thead><tr><th>#</th><th>시나리오</th><th>동작 · 흐름도와 다른 점</th><th>대조</th><th>트리거</th><th>data 에 쓴 파일</th></tr></thead>
    <tbody id="tbl"></tbody>
  </table></div>

  <h2>확인 결과 ({ok_n}/{len(R)})</h2>
  <p class="sub">시나리오 재생 하네스의 확인 항목 전부. 기능 번호는 <code>v4a_design.md</code> §8 · 결정 번호는 <code>v4a_decisions.md</code>.</p>
  <div class="tbl-scroll"><table>
    <thead><tr><th>시나리오</th><th>기능·결정</th><th>확인</th><th>결과</th></tr></thead>
    <tbody>{"".join(res_rows)}</tbody>
  </table></div>

  <h2>검증 중 발견해 고친 결함</h2>
  <div class="tbl-scroll"><table>
    <thead><tr><th>결함</th><th>내용</th><th>수정 커밋</th></tr></thead>
    <tbody>{fixed_rows}</tbody>
  </table></div>

</div>
<script>{script}</script>
</body>
</html>
'''
out = head + "<style>" + style + "</style>\n</head>\n" + body
OUT.write_text(out, encoding="utf-8")
print("written", OUT, len(out), "bytes ·", len(F_js), "actions ·", len(groups), "groups")
