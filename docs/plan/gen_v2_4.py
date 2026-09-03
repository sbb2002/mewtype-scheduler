"""v2_4_flow.png 생성 — 현행(v2.4) X 릴레이 + 합동방송 + ingest 큐 전체 흐름.

외부(운영자 폰) · 백엔드 · 프론트엔드를 점선 그룹 박스로 묶는다.

    python docs/plan/gen_v2_4.py
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

for _name in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"):
    if any(f.name == _name for f in fm.fontManager.ttflist):
        plt.rcParams["font.family"] = _name
        break
plt.rcParams["axes.unicode_minus"] = False

GREEN, GREEN_E = "#e3f0e0", "#7fae7a"
BLUE, BLUE_E = "#dde8f4", "#6f9bce"
ORANGE, ORANGE_E = "#fdeccd", "#d8a24a"
PURPLE, PURPLE_E = "#e6e0f0", "#9a86c8"
GRAY, GRAY_E = "#eceae6", "#9a978f"
INK = "#2b2b2b"

fig, ax = plt.subplots(figsize=(12.4, 8.4), dpi=160)
ax.set_xlim(0, 124)
ax.set_ylim(0, 84)
ax.axis("off")


def box(x, y, w, h, text, fc, ec, *, fs=8.2):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                boxstyle="round,pad=0.5,rounding_size=1.3", fc=fc, ec=ec, lw=1.5))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, weight="bold", color=INK)


def group(x, y, w, h, text):
    ax.add_patch(Rectangle((x, y), w, h, fill=False, ec="#3a3a3a", lw=1.4, ls=(0, (6, 4))))
    ax.text(x + 2.2, y + h - 2.6, text, fontsize=10.5, weight="bold", color=INK)


def arrow(p0, p1, *, rad=0.0, ls="-", lw=1.5):
    ax.add_patch(FancyArrowPatch(p0, p1, connectionstyle=f"arc3,rad={rad}",
                arrowstyle="-|>", mutation_scale=14, lw=lw, ls=ls, color="#3a3a3a"))


def label(x, y, t, *, fs=7.6):
    ax.text(x, y, t, ha="center", va="center", fontsize=fs, color="#4a4a4a")


ax.text(62, 80.5, "v2.4 — X 릴레이 · 합동방송 · ingest 큐 (현행)",
        ha="center", va="center", fontsize=15, weight="bold", color=INK)

# ── 그룹 1: 외부 (운영자 폰) ─────────────────────────────
group(3, 40, 34, 36, "외부  ·  운영자 폰")
box(5.5, 60, 29, 13,
    "S23 · Automate\n삼성 브라우저 웹푸시 알림\n@BDP_yumemita\n일일 스케줄 트윗", BLUE, BLUE_E, fs=7.9)
box(5.5, 43, 29, 12,
    "운영자 Telegram DM\n· ECHO 원문 + tail_ok (말미문구 O/X)\n· 반영 결과 / 대기열 N건", BLUE, BLUE_E, fs=7.8)

# ── 그룹 2: 백엔드 (Cloud Run + GitHub) ──────────────────
group(41, 6, 55, 70, "백엔드  ·  Cloud Run + GitHub data 브랜치")
box(43.5, 55, 50, 18,
    "mewtype-telegram  (공개)\nPOST /ingest  ·  X-Ingest-Secret 검증\n"
    "─ 테스트 (INGEST_ECHO=1 또는 DRY_RUN=1)\n"
    "    파싱 안 함 → DM(tail_ok 로그) + ingest_queue.json 적재\n"
    "─ 실배포 (ECHO=0 · DRY_RUN=0)\n"
    "    큐 drain → xrelay.parse_bdp_schedule → merge_scheduled",
    GREEN, GREEN_E, fs=7.6)
box(43.5, 37, 50, 11,
    "GitHub  data 브랜치\nschedule.json   ·   ingest_queue.json\n"
    "(scheduled 행: video_id 없음 · host=group)",
    ORANGE, ORANGE_E, fs=7.8)
box(43.5, 15, 50, 17,
    "mewtype-backend   ·   정기 /tick (Cloud Scheduler)\nreconcile.build_schedule\n"
    "· scheduled 보존 · 같은 채널 실물 ±4h → supersede\n"
    "· expires_at(start+3~5h) 도달 → 제거\n"
    "· host=group 은 멤버 개인 실물로 supersede 안 함 (TTL 로만)",
    GREEN, GREEN_E, fs=7.4)

# ── 그룹 3: 프론트엔드 (Vercel) ─────────────────────────
group(100, 26, 22, 34, "프론트엔드")
box(102, 30, 18, 26,
    "프론트 (Vercel)\n75s 폴링\n\n.card--scheduled\n(예고)\n\n.card--collab\n합동 → 참여 멤버\n전원 레인 팬아웃",
    PURPLE, PURPLE_E, fs=7.7)

# ── 모드 스위치 노트 ──
box(3, 20, 34, 14,
    "모드 스위치 (env)\nINGEST_ECHO · INGEST_DRY_RUN\n1 = 테스트 — 큐에 쌓기만\n0 + 0 = 실배포 — 큐 drain + schedule 반영",
    GRAY, GRAY_E, fs=7.6)
arrow((28, 34), (43.5, 59), rad=-0.12, ls="--")

# ── 화살표 ──
arrow((34.5, 66), (43.5, 65), rad=-0.05)
label(39.5, 69, "알림 본문 text=")

arrow((43.5, 60), (34.5, 50), rad=0.12)
label(38, 56.5, "DM 회신")

arrow((68, 55), (68, 48), rad=0)
label(80.5, 51.5, "큐 적재 (테스트)\nschedule.json 커밋 (실배포)")

arrow((60, 37), (60, 32), rad=0)
arrow((76, 32), (76, 37), rad=0)
label(68, 34.5, "reconcile\n보존 · 정리")

arrow((93.5, 43), (100, 43), rad=0)
label(96.7, 45.6, "raw fetch")

fig.tight_layout(pad=0.4)
out = __file__.replace("\\", "/").rsplit("/", 1)[0] + "/v2_4_flow.png"
fig.savefig(out, dpi=160)
print("wrote", out)
