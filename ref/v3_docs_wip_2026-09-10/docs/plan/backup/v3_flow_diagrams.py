# -*- coding: utf-8 -*-
"""v3 흐름 다이어그램 — v3_ARCH_DIAGRAM.png 스타일(컨테이너 뷰).
관여하지 않는 요소는 그리지 않는다. 3장:
  v3_TELEGRAM_FLOW.png  — 텔레그램 명령어 흐름
  v3_SCHEDULE_FLOW.png  — 스케줄 인프라 흐름
  v3_STATE_MACHINE.png  — 예고 아이템 6상태 생애주기
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


def box(ax, x, y, w, h, title, sub="", color=C_SVC, dashed=False, tfs=10.5):
    ax.add_patch(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.6", linewidth=1.4,
        edgecolor="#333", facecolor=color, linestyle="--" if dashed else "-"))
    cx, cy = x + w / 2, y + h / 2
    if sub:
        ax.text(cx, cy + h * 0.17, title, ha="center", va="center", fontsize=tfs, fontweight="bold")
        ax.text(cx, cy - h * 0.22, sub, ha="center", va="center", fontsize=7.6, color="#333")
    else:
        ax.text(cx, cy, title, ha="center", va="center", fontsize=tfs, fontweight="bold")


def arrow(ax, p1, p2, label="", rad=0.0, dashed=False, both=False,
          lx=None, ly=None, fs=7.4, color="#333"):
    ax.annotate("", xy=p2, xytext=p1, arrowprops=dict(
        arrowstyle="<|-|>" if both else "-|>", color=color, linewidth=1.3,
        linestyle="--" if dashed else "-", connectionstyle=f"arc3,rad={rad}",
        shrinkA=2, shrinkB=2))
    if label:
        ax.text(lx if lx is not None else (p1[0] + p2[0]) / 2,
                ly if ly is not None else (p1[1] + p2[1]) / 2,
                label, ha="center", va="center", fontsize=fs,
                bbox=dict(boxstyle="round,pad=0.3", fc="white", ec="#999", lw=0.8))


def elbow(ax, pts, label="", lx=None, ly=None, fs=7.2, dashed=False, color="#333"):
    """직각으로만 꺾이는 연결선. pts = [(x,y), ...] 순서대로. 마지막 구간에 화살촉."""
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
        edgecolor="#b58", facecolor="#fdf4f7"))
    ax.text(x + 0.6, y + h - 0.7,
            ((title + "\n") if title else "") + text,
            ha="left", va="top", fontsize=fs, color="#333")


def canvas(w, h, title):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    ax.text(1, 99, title, ha="left", va="top", fontsize=15, fontweight="bold")
    return fig, ax


def save(fig, name):
    fig.tight_layout()
    fig.savefig(f"{OUT}\\{name}", dpi=130, bbox_inches="tight")
    plt.close(fig)


# ==================================================== 1. 텔레그램 명령어 흐름
fig, ax = canvas(16, 11, "v3 — 텔레그램 명령어 흐름")

box(ax, 78, 82, 19, 12, "운영자", "(사용자)", C_ACT)
box(ax, 40, 82, 30, 12, "제어 채널 창구", "Telegram · transport", C_EXT)
box(ax, 40, 52, 30, 16, "제어 채널", "Cloud Run · mewtype-telegram\n명령 처리 · 되묻기 FSM", C_SVC)
box(ax, 6, 52, 26, 16, "외부 LLM", "Groq · gpt-oss-120b\n제목/본문 번역", C_LLM, dashed=True)
box(ax, 78, 52, 19, 16, "백엔드", "Cloud Run · mewtype-backend\n/tick · /wake", C_SVC)
box(ax, 40, 22, 30, 16, "DB", "GitHub · data 브랜치\npreview · notices · tweets · admin_state · control", C_DB)

arrow(ax, (78, 88), (70, 88), "명령  ↔  되묻기 · 응답", both=True, ly=90.6)
arrow(ax, (55, 82), (55, 68), "webhook")
arrow(ax, (40, 60), (32, 60), "/translate · 번역 왕복", both=True, ly=62.4)
arrow(ax, (70, 60), (78, 60), "/resume → /tick 호출")
arrow(ax, (52, 52), (52, 38),
      "읽기   /status · /list · /log\n쓰기   /ingest · /edit · /del · /undo\n"
      "          /pause · /resume → control.json",
      lx=34, ly=45.5, fs=7.2)
arrow(ax, (80, 52), (64, 39), "edit_lock · suppress 읽고\n그 id preview.json 커밋만 스킵",
      dashed=True, rad=-0.22, lx=86, ly=46, fs=7.0)

note(ax, 2, 2, 62, 19, fs=7.6, title="명령 → 경로",
     text="· /status /list /log        제어 채널 → DB 읽기 → 응답\n"
          "· /ingest [c]               되묻기 → 원문 파싱 → DB 쓰기 (번역 없음)\n"
          "· /edit /del [c]            /list → idx(=id 대조) → edit_lock →\n"
          "                            답한 필드만 patch → DB 쓰기 → 충돌 시 알림 1개\n"
          "· /del …(terminate)        + suppress[url] = now + 12h (재진입 차단)\n"
          "· /undo                     admin_state 슬롯 → 직전 mutating 1건 롤백\n"
          "· /translate [c]            제어 채널 → 외부 LLM → 원문+번역 DB 쓰기\n"
          "· /pause /resume            control.json(paused). /resume 는 백엔드 /tick 호출")
note(ax, 66, 2, 32, 19, fs=7.6, title="가드 규칙",
     text="· 되묻기 각 단계 60초 무응답 → 자동취소\n"
          "· 아무 단계에서 aNoneTokyo → 명령 취소\n"
          "· edit_lock 중에도 백엔드는 안 멈춘다 —\n"
          "  그 id 의 preview.json 커밋만 이번 사이클 스킵\n"
          "· idx 는 방금 /list 스냅샷 전용, 실타깃은 id\n"
          "· 번역은 원문 보존 · *_ko 병렬 필드")
save(fig, "v3_TELEGRAM_FLOW.png")


# ==================================================== 2. 스케줄 인프라 흐름
#   직선(수평·수직)만 사용. 어떤 선도 다른 선·박스를 건너지 않는다 (평면 배치).
fig, ax = canvas(16, 10, "v3 — 스케줄 인프라 흐름")

box(ax, 3, 76, 17, 14, "Cloud Scheduler", "GCP 트리거\nbaseline 06:00 / light 3h", C_EXT)
box(ax, 3, 56, 17, 14, "Cloud Tasks", "GCP · 방송별 wake", C_EXT)
box(ax, 3, 36, 17, 14, "YouTube Data API", "서드파티\nRSS + videos.list", C_EXT)
box(ax, 28, 44, 22, 44, "백엔드", "mewtype-backend\n/tick · /wake · reconcile\n(FSM 파생)", C_SVC)
box(ax, 58, 72, 22, 16, "제어 채널 창구", "Telegram · DM", C_EXT)
box(ax, 58, 44, 22, 22, "제어 채널", "mewtype-telegram\nPOST /ingest 파싱\n(xrelay·xnotice·xtweet)", C_SVC)
box(ax, 58, 16, 14, 20, "외부 LLM", "Groq\n파이프라인 끝 번역", C_LLM, dashed=True)
box(ax, 84, 44, 14, 20, "업스트림 시스템", "운영자 폰\n+ Automate\nX·YT 알림", C_EXT, tfs=9)
box(ax, 28, 2, 52, 12, "DB", "GitHub · data 브랜치\npreview.json · notices · tweets", C_DB)

arrow(ax, (20, 83), (28, 83), "POST /tick · OIDC", ly=85.5, fs=7.0)
arrow(ax, (20, 63), (28, 63), "POST /wake · enqueue", both=True, ly=65.5, fs=7.0)
arrow(ax, (20, 46), (28, 46), "RSS · videos.list", both=True, ly=48.5, fs=7.0)
arrow(ax, (50, 80), (58, 80), "상태전이 DM 알림", ly=82.5, fs=7.0)
arrow(ax, (58, 52), (50, 52), "커밋분을 다음 /tick 이\nreconcile·보존", dashed=True, lx=54, ly=57, fs=6.4, color="#666")
arrow(ax, (84, 54), (80, 54), "POST /ingest", ly=56.5, fs=7.0)
arrow(ax, (65, 44), (65, 36), "번역 (자동)", lx=71, ly=40, fs=6.8)
elbow(ax, [(40, 44), (40, 26), (58, 26)], "번역 (제목/본문)", lx=48, ly=23, fs=6.8)
arrow(ax, (35, 44), (35, 14), "preview.json 커밋 (변경분만)", lx=27, ly=29, fs=6.8)
arrow(ax, (76, 44), (76, 14), "notices·tweets·\nscheduled 커밋", lx=85, ly=29, fs=6.6)

note(ax, 3, 16, 17, 16, fs=7.2, title="게이트·지연",
     text="control.json=paused\n→ /tick·/wake no-op\n(healthcheck 핑만)\n\n"
          "프론트는 raw JSON\n75초 폴링, CDN 캐시\n최대 ~5분 지연")
save(fig, "v3_SCHEDULE_FLOW.png")


# ==================================================== 3. 6상태 생애주기 (FSM)
#   직선·직각만. 여백 최소화.
fig, ax = canvas(16, 6.6, "v3 — 예고 아이템 6상태 생애주기")
ax.text(1, 92, "FSM 은 저장 타이머 없이 state · scheduled_start · actual_start · state_since · now 로 파생  ·  "
        "none → announced → (upcoming) → (watching) → live <-> end → none",
        ha="left", va="top", fontsize=8.3, color="#555")

sy, sh = 66, 13
S = {  # key: (x, w, 한줄설명)
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

# end -> live (되살아남): 두 박스 사이 틈으로 내려갔다 올라옴 (직각, desc 아래)
lx_e = S["end"][0] + 2; lx_l = S["live"][0] + S["live"][1] - 2
elbow(ax, [(lx_e, sy), (lx_e, sy - 8), (lx_l, sy - 8), (lx_l, sy)],
      "다시 켜짐", lx=(lx_e + lx_l) / 2, ly=sy - 8, fs=6.6)
# end -> none (긴 복귀): 체인 아래로 직각 U
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
ax.set_ylim(24, 100)  # 아래 여백 제거
save(fig, "v3_STATE_MACHINE.png")
print("done")
