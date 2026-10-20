# -*- coding: utf-8 -*-
"""v3 흐름 다이어그램. 3장:
  v3_TELEGRAM_FLOW.png  — 텔레그램 명령어 흐름  (아키텍처 컨테이너 뷰 재활용)
  v3_SCHEDULE_FLOW.png  — 스케줄 인프라 흐름    (아키텍처 컨테이너 뷰 재활용)
  v3_STATE_MACHINE.png  — 예고 아이템 6상태 생애주기

앞 2장은 v3_ARCH_DIAGRAM.png 와 같은 박스 배치를 쓰고,
  · 그 기능에 관여하지 않는 박스 = 반투명
  · 그 기능이 쓰는 화살표 = 진한 실선 화살표 + 라벨
  · 안 쓰는 연결 = 옅은 실선(화살촉·라벨 없음)으로 '연결만 있음' 표시
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.family"] = "Malgun Gothic"
plt.rcParams["axes.unicode_minus"] = False

OUT = r"C:\Users\user\Documents\myprojects\mewtype-scheduler\docs\plan"
C_EXT = "#e9e9e9"; C_SVC = "#cfe0f5"; C_DB = "#d3ebd0"
C_LLM = "#e7d6f7"; C_ACT = "#fce9b8"; C_ST = "#dbe7f6"


def box(ax, x, y, w, h, title, sub="", color=C_SVC, dashed=False, tfs=10.5, alpha=1.0):
    ec = "#333" if alpha >= 0.99 else "#aaa"
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.6", linewidth=1.4,
        edgecolor=ec, facecolor=color, linestyle="--" if dashed else "-",
        alpha=alpha, zorder=2))
    cx, cy = x + w / 2, y + h / 2
    tc = "#111" if alpha >= 0.99 else "#999"
    sc = "#333" if alpha >= 0.99 else "#aaa"
    if sub:
        ax.text(cx, cy + h * 0.17, title, ha="center", va="center", fontsize=tfs,
                fontweight="bold", color=tc, alpha=alpha, zorder=3)
        ax.text(cx, cy - h * 0.22, sub, ha="center", va="center", fontsize=7.4,
                color=sc, alpha=alpha, zorder=3)
    else:
        ax.text(cx, cy, title, ha="center", va="center", fontsize=tfs,
                fontweight="bold", color=tc, alpha=alpha, zorder=3)


def arrow(ax, p1, p2, label="", rad=0.0, dashed=False, both=False,
          lx=None, ly=None, fs=7.4, color="#333"):
    ax.annotate("", xy=p2, xytext=p1, zorder=5, arrowprops=dict(
        arrowstyle="<|-|>" if both else "-|>", color=color, linewidth=1.6,
        linestyle="--" if dashed else "-", connectionstyle=f"arc3,rad={rad}",
        shrinkA=3, shrinkB=3))
    if label:
        ax.text(lx if lx is not None else (p1[0] + p2[0]) / 2,
                ly if ly is not None else (p1[1] + p2[1]) / 2,
                label, ha="center", va="center", fontsize=fs, zorder=6,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#999", lw=0.8))


def faint(ax, p1, p2):
    ax.plot([p1[0], p2[0]], [p1[1], p2[1]], color="#c8c8c8", lw=1.0,
            alpha=0.6, zorder=0, solid_capstyle="round")


def elbow(ax, pts, label="", lx=None, ly=None, fs=7.2, dashed=False, color="#333"):
    ls = "--" if dashed else "-"
    for a, b in zip(pts[:-2], pts[1:-1]):
        ax.plot([a[0], b[0]], [a[1], b[1]], color=color, lw=1.3, ls=ls, solid_capstyle="round")
    ax.annotate("", xy=pts[-1], xytext=pts[-2], arrowprops=dict(
        arrowstyle="-|>", color=color, linewidth=1.3, linestyle=ls, shrinkA=0, shrinkB=2))
    if label:
        ax.text(lx, ly, label, ha="center", va="center", fontsize=fs,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#999", lw=0.8))


def note(ax, x, y, w, h, text, title=None, fs=8.0):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.5", linewidth=1.0,
        edgecolor="#b58", facecolor="#fdf4f7", zorder=2))
    ax.text(x + 0.6, y + h - 0.7, ((title + "\n") if title else "") + text,
            ha="left", va="top", fontsize=fs, color="#333", zorder=3)


def canvas(w, h, title):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    ax.text(1, 99, title, ha="left", va="top", fontsize=14.5, fontweight="bold")
    return fig, ax


def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"{OUT}\\{name}", dpi=130, bbox_inches="tight")
    plt.close(fig)


# ================================================================= 아키텍처 배치 (공용)
NODES = {
    "operator": dict(x=75, y=83, w=15, h=11, t="운영자",           s="(사용자)",                         c=C_ACT),
    "gateway":  dict(x=43, y=83, w=27, h=11, t="제어 채널 창구",     s="Telegram · transport",             c=C_EXT),
    "push":     dict(x=1,  y=49, w=15, h=14, t="X·YouTube\n푸시알림", s="서드파티 · 신호원",                 c=C_EXT, tfs=8.5),
    "upstream": dict(x=19, y=49, w=17, h=14, t="업스트림 시스템",     s="운영자 폰 + Automate",              c=C_EXT, tfs=8.5),
    "telegram": dict(x=40, y=47, w=19, h=16, t="제어 채널",          s="mewtype-telegram\n/ingest · 운영 명령", c=C_SVC),
    "backend":  dict(x=63, y=47, w=19, h=16, t="백엔드",             s="mewtype-backend\n/tick /wake · 판정",   c=C_SVC),
    "sched":    dict(x=85, y=49, w=14, h=14, t="Cloud Scheduler\n/ Tasks", s="GCP · 트리거",               c=C_EXT, tfs=8.5),
    "ytapi":    dict(x=85, y=31, w=14, h=13, t="YouTube Data API",   s="서드파티\nRSS + videos.list",       c=C_EXT, tfs=8.5),
    "llm":      dict(x=16, y=29, w=20, h=13, t="외부 LLM",           s="Groq · 제목추출·번역",             c=C_LLM, dashed=True, tfs=9),
    "db":       dict(x=44, y=25, w=22, h=14, t="DB",                 s="GitHub · data 브랜치\n(커밋 = write)",  c=C_DB),
    "front":    dict(x=44, y=8,  w=22, h=13, t="프론트엔드",          s="Vercel · 폴링 렌더",               c=C_SVC),
    "fan":      dict(x=47, y=-6, w=16, h=10, t="팬",                 s="(사용자)",                         c=C_ACT, tfs=10),
}


def anc(k, side, f=0.5):
    n = NODES[k]; x, y, w, h = n["x"], n["y"], n["w"], n["h"]
    return {"t": (x + w * f, y + h), "b": (x + w * f, y),
            "l": (x, y + h * f), "r": (x + w, y + h * f)}[side]


# (id, n1, s1, f1, n2, s2, f2, 기본라벨, both?)
EDGES = [
    ("E1",  "operator", "l", .5, "gateway", "r", .5, "명령",              True),
    ("E2",  "gateway",  "b", .5, "telegram", "t", .5, "webhook",          True),
    ("E3",  "backend",  "t", .3, "gateway", "b", .7, "상태전이 DM 알림",   False),
    ("E4",  "push",     "r", .5, "upstream", "l", .5, "푸시 알림",         False),
    ("E5",  "upstream", "r", .5, "telegram", "l", .5, "POST /ingest",     False),
    ("E6",  "telegram", "b", .5, "db", "t", .25, "control.json·admin",    False),
    ("E7",  "backend",  "b", .5, "db", "t", .75, "Contents API 커밋",     False),
    ("E8",  "backend",  "r", .5, "sched", "l", .5, "/tick · /wake (OIDC)", True),
    ("E9",  "ytapi",    "t", .4, "backend", "b", .85, "RSS · videos.list", False),
    ("E10", "llm",      "r", .5, "telegram", "b", .15, "제목추출·번역(v3)", True),
    ("E11", "db",       "b", .5, "front", "t", .5, "raw JSON · 75초 폴링", False),
    ("E12", "front",    "b", .5, "fan", "t", .5, "사이트 표시",           False),
    ("E13", "telegram", "r", .8, "backend", "l", .8, "/resume → /tick",   True),
]
EMAP = {e[0]: e for e in EDGES}


def render_arch(title, active_nodes, active_edges, labels, legend):
    fig, ax = canvas(15.5, 11, title)
    # 옅은 연결선 먼저 (안 쓰는 경로 전부)
    for eid, n1, s1, f1, n2, s2, f2, lbl, both in EDGES:
        if eid not in active_edges:
            faint(ax, anc(n1, s1, f1), anc(n2, s2, f2))
    # 박스
    for k, n in NODES.items():
        a = 1.0 if k in active_nodes else 0.20
        box(ax, n["x"], n["y"], n["w"], n["h"], n["t"], n.get("s", ""),
            n["c"], n.get("dashed", False), n.get("tfs", 10.5), alpha=a)
    # 쓰는 화살표
    for eid in active_edges:
        _, n1, s1, f1, n2, s2, f2, lbl, both = EMAP[eid]
        arrow(ax, anc(n1, s1, f1), anc(n2, s2, f2),
              labels.get(eid, lbl), both=both, dashed=(eid in ("E10", "E13")), fs=7.0)
    ax.text(1, -8, legend, ha="left", va="top", fontsize=7.6, color="#555")
    ax.set_ylim(-10, 100)
    return fig


LEGEND = ("진한 화살표 = 이 기능이 실제로 쓰는 경로   ·   반투명 박스 = 이 기능에 관여하지 않는 요소   ·   "
          "옅은 실선 = 연결은 있으나 이 기능에선 안 쓰임")

# ---------- 1. 텔레그램 명령어 흐름 ----------
fig = render_arch(
    "v3 — 텔레그램 명령어 흐름   (아키텍처 컨테이너 뷰 · 이 기능이 쓰는 경로만 강조)",
    active_nodes={"operator", "gateway", "telegram", "db", "llm", "backend"},
    active_edges={"E1", "E2", "E6", "E10", "E13"},
    labels={
        "E1": "명령  ·  되묻기 / 응답",
        "E2": "webhook",
        "E6": "DB 읽기/쓰기\n/list·/ingest·/edit·/del·/undo\n/pause·/resume·edit_lock",
        "E10": "/translate · 번역 왕복",
        "E13": "/resume → /tick 호출",
    },
    legend=LEGEND)
save(fig, "v3_TELEGRAM_FLOW.png")

# ---------- 2. 스케줄 인프라 흐름 ----------
fig = render_arch(
    "v3 — 스케줄 인프라 흐름   (아키텍처 컨테이너 뷰 · 이 기능이 쓰는 경로만 강조)",
    active_nodes={"push", "upstream", "telegram", "backend", "sched", "ytapi", "db", "llm", "gateway"},
    active_edges={"E3", "E4", "E5", "E6", "E7", "E8", "E9", "E10", "E13"},
    labels={
        "E3": "상태전이 DM 알림",
        "E4": "푸시 알림",
        "E5": "POST /ingest\n(X 트윗 · YT 앱 알림)",
        "E6": "notices·tweets·\nscheduled 커밋",
        "E7": "preview.json 커밋\n(변경분만)",
        "E8": "/tick · /wake (OIDC)\nbaseline 06:00 / light 3h",
        "E9": "RSS · videos.list",
        "E10": "파이프라인 끝 번역",
        "E13": "커밋분 → 다음 /tick reconcile",
    },
    legend=LEGEND + "\ncontrol.json = paused → /tick·/wake no-op   ·   프론트는 raw JSON 75초 폴링(CDN 캐시 ~5분)")
save(fig, "v3_SCHEDULE_FLOW.png")


# ================================================================= 3. 6상태 생애주기 (FSM)
fig, ax = canvas(16, 6.6, "v3 — 예고 아이템 6상태 생애주기")
ax.text(1, 92, "FSM 은 저장 타이머 없이 state · scheduled_start · actual_start · state_since · now 로 파생  ·  "
        "none → announced → (upcoming) → (watching) → live <-> end → none",
        ha="left", va="top", fontsize=8.3, color="#555")

sy, sh = 66, 13
S = {
    "none":      (3,  12, "정보·아이템 없음"),
    "announced": (18, 15, "예고 감지 · 일부 정보"),
    "upcoming":  (36, 15, "날짜·시각·제목·썸네일·url"),
    "watching":  (54, 15, "start-3분부터 3분 간격"),
    "live":      (72, 11, "방송 중(n분)"),
    "end":       (85, 12, "방송 종료 · 영상 유지"),
}
for k, (x, w, desc) in S.items():
    box(ax, x, sy, w, sh, k, "", C_ST, tfs=11)
    ax.text(x + w / 2, sy - 1.5, desc, ha="center", va="top", fontsize=6.8, color="#555")


def fwd(k1, k2, label):
    x1 = S[k1][0] + S[k1][1]; x2 = S[k2][0]; y = sy + sh / 2
    arrow(ax, (x1, y), (x2, y), label, lx=(x1 + x2) / 2, ly=sy + sh + 4, fs=6.8)


fwd("none", "announced", "예고 감지")
fwd("announced", "upcoming", "5필드 전부\n(YT TUNEIN/트윗)")
fwd("upcoming", "watching", "start - 3분")
fwd("watching", "live", "라이브 확인")
fwd("live", "end", "종료 확인")

lx_e = S["end"][0] + 2; lx_l = S["live"][0] + S["live"][1] - 2
elbow(ax, [(lx_e, sy), (lx_e, sy - 8), (lx_l, sy - 8), (lx_l, sy)],
      "다시 켜짐", lx=(lx_e + lx_l) / 2, ly=sy - 8, fs=6.6)
ex = S["end"][0] + S["end"][1] / 2; nx = S["none"][0] + S["none"][1] / 2
elbow(ax, [(ex, sy), (ex, sy - 18), (nx, sy - 18), (nx, sy)],
      "state_since + 30분 (5분 간격 확인, 계속 종료 유지)  ·  마지막 확인에서 예고 스트림이면 upcoming 복귀",
      lx=48, ly=sy - 18, fs=6.9)

note(ax, 3, 27, 55, 15, fs=7.6, title="파생 규칙",
     text="· watching   3분 간격 live 체크 · 지각 120분 → announced 강등(url 유지)\n"
          "             · 최신 예고 정보 오면 → upcoming 복귀\n"
          "· live       actual_start+60분까지 10분 간격, 이후 3분 간격\n"
          "· assumed-live 폴백   video_id 못 얻고 start+90분 → none\n"
          "                      (프론트: '방송 중(추정)')")
note(ax, 61, 27, 36, 15, fs=7.6, title="회원전용 (membership: true)",
     text="· videos.list 404 → API wake 안 탐\n"
          "· watching 스킵 — 시작 알림 오면 live 직행\n"
          "· 종료 판정 불가 → 시간 기반 폴백(N시간)\n"
          "  이후 RSS 아카이브로 사후 확정\n"
          "· 착수 트리거: 이 알림 실제로 와야 v3 시작")
ax.set_ylim(24, 100)
save(fig, "v3_STATE_MACHINE.png")
print("done")
