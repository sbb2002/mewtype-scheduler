"""v2_4_flow.png 생성 — 현행(v2.4) 구성요소 관계도 (박스 이름만).

각 박스의 상세 동작은 docs/plan/v2_4_golive.md · v2_4_collab.md 본문 참고.
화살표는 그룹 내부 아니면 그룹 사이 여백에만 두어 점선 테두리와 겹치지 않게 한다.

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
INK = "#2b2b2b"

fig, ax = plt.subplots(figsize=(11.6, 6.4), dpi=170)
ax.set_xlim(0, 116)
ax.set_ylim(0, 64)
ax.axis("off")

# 그룹 x-경계와 그 사이 여백
A_R = 33          # 외부 그룹 오른쪽 경계
B_L, B_R = 42, 88  # 백엔드 그룹 경계
C_L = 96          # 프론트 그룹 왼쪽 경계


def box(x, y, w, h, text, fc, ec, *, fs=9):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                boxstyle="round,pad=0.5,rounding_size=1.3", fc=fc, ec=ec, lw=1.6))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, weight="bold", color=INK)


def group(x, y, w, h, text):
    ax.add_patch(Rectangle((x, y), w, h, fill=False, ec="#3a3a3a", lw=1.4, ls=(0, (6, 4))))
    ax.text(x + 2.2, y + h - 2.4, text, fontsize=10, weight="bold", color=INK)


def arrow(p0, p1, *, rad=0.0, ls="-", lw=1.6):
    ax.add_patch(FancyArrowPatch(p0, p1, connectionstyle=f"arc3,rad={rad}",
                arrowstyle="-|>", mutation_scale=15, lw=lw, ls=ls, color="#3a3a3a"))


def label(x, y, t, *, fs=8):
    ax.text(x, y, t, ha="center", va="center", fontsize=fs, color="#4a4a4a")


ax.text(58, 60.5, "v2.4 — X 릴레이 · 합동방송 · ingest 큐  (구성요소)",
        ha="center", va="center", fontsize=14.5, weight="bold", color=INK)

# ── 그룹 1: 외부 ──────────────────────────────────────
group(3, 20, 30, 34, "외부  ·  운영자 폰")
box(6, 40, 25, 10, "Android · Automate\n(삼성 브라우저 웹푸시)", BLUE, BLUE_E)
box(6, 24, 25, 10, "운영자 Telegram DM", BLUE, BLUE_E)

# ── 그룹 2: 백엔드 ────────────────────────────────────
group(B_L, 8, B_R - B_L, 46, "백엔드  ·  Cloud Run + GitHub")
box(48, 41, 34, 9, "mewtype-telegram\nPOST /ingest", GREEN, GREEN_E)
box(48, 27, 34, 9, "GitHub  data 브랜치\nschedule.json · ingest_queue.json", ORANGE, ORANGE_E, fs=8)
box(48, 13, 34, 9, "mewtype-backend\n정기 /tick · reconcile", GREEN, GREEN_E)

# ── 그룹 3: 프론트엔드 ────────────────────────────────
group(C_L, 27, 18, 20, "프론트엔드")
box(99, 32, 12, 10, "프론트\n(Vercel)", PURPLE, PURPLE_E)

# ── 화살표 (그룹 사이는 여백에서 경계↔경계) ─────────────
arrow((A_R, 45), (B_L, 45))
label((A_R + B_L) / 2, 47.5, "알림 본문")
arrow((B_L, 29), (A_R, 29))
label((A_R + B_L) / 2, 31.5, "ECHO / 결과 DM")

arrow((65, 41), (65, 36))
label(73, 38.5, "커밋 / 큐")
arrow((60, 27), (60, 22))
arrow((70, 22), (70, 27))
label(65, 24.5, "reconcile")

arrow((B_R, 37), (C_L, 37))
label((B_R + C_L) / 2, 39.5, "raw fetch")

fig.tight_layout(pad=0.4)
out = __file__.replace("\\", "/").rsplit("/", 1)[0] + "/v2_4_flow.png"
fig.savefig(out, dpi=170)
print("wrote", out)
