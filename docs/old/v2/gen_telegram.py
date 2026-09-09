"""v2_1_telegram.png 생성 스크립트 — v2.1 Telegram 모니터링/제어 레이어.

    python docs/plan/gen_telegram.py
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

for _name in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"):
    if any(f.name == _name for f in fm.fontManager.ttflist):
        plt.rcParams["font.family"] = _name
        break
plt.rcParams["axes.unicode_minus"] = False

GREEN, GREEN_E = "#e3f0e0", "#7fae7a"
BLUE, BLUE_E = "#dde8f4", "#6f9bce"
ORANGE, ORANGE_E = "#fdeccd", "#d8a24a"
GRAY, GRAY_E = "#eceae6", "#9a978f"
INK = "#2b2b2b"

fig, ax = plt.subplots(figsize=(10.6, 6.6), dpi=160)
ax.set_xlim(0, 106)
ax.set_ylim(0, 66)
ax.axis("off")


def box(x, y, w, h, text, fc, ec, *, fs=9):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                boxstyle="round,pad=0.6,rounding_size=1.4", fc=fc, ec=ec, lw=1.6))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, weight="bold", color=INK)


def arrow(p0, p1, *, rad=0.0, ls="-", lw=1.6):
    ax.add_patch(FancyArrowPatch(p0, p1, connectionstyle=f"arc3,rad={rad}",
                arrowstyle="-|>", mutation_scale=15, lw=lw, ls=ls, color="#3a3a3a"))


def label(x, y, t, *, fs=8.3):
    ax.text(x, y, t, ha="center", va="center", fontsize=fs, color="#4a4a4a")


ax.text(53, 63.5, "v2.1 — Telegram 모니터링 & 제어",
        ha="center", va="center", fontsize=15, weight="bold", color=INK)

# 운영자 / Telegram
box(38, 52, 30, 8, "운영자  (Telegram DM)", BLUE, BLUE_E)
box(38, 40, 30, 7, "Telegram Bot API", BLUE, BLUE_E, fs=8.5)
arrow((49, 52), (49, 47), rad=0)          # 운영자 → botapi (명령)
arrow((57, 47), (57, 52), rad=0)          # botapi → 운영자 (알림/회신)
label(41.5, 49.5, "명령")
label(64.5, 49.5, "알림·회신")

# 백엔드 서비스 2개
box(6, 24, 30, 13, "mewtype-backend\n(메인 · 비공개 · OIDC)", GREEN, GREEN_E, fs=8.7)
box(60, 24, 34, 13, "mewtype-telegram\n(공개 webhook · INVOKER_SA)", GREEN, GREEN_E, fs=8.5)

arrow((24, 37), (40, 40), rad=-0.18)      # 메인 → botapi (알림 A~F)
label(33, 43, "알림 A~F (sendMessage)")
arrow((66, 40), (74, 37), rad=-0.15)      # botapi → telegram (webhook)
label(76.5, 41, "webhook\n/status /pause /resume")

arrow((60, 30.5), (36, 30.5), rad=0.0)    # telegram → 메인 (/resume)
label(48, 32.6, "/resume → OIDC → POST /tick")

# data 브랜치
box(30, 6, 46, 10,
    "GitHub  `data` 브랜치\nschedule · archive · pending · control.json",
    ORANGE, ORANGE_E, fs=8.7)
arrow((77, 24), (66, 16), rad=-0.12)      # telegram → data (control R/W, status read)
label(86, 19.5, "control.json R/W\nschedule/pending read")
arrow((18, 24), (34, 16), rad=0.12)       # 메인 → data (가드 read + 커밋)
arrow((34, 16), (18, 24), rad=0.12)
label(8, 18.5, "control.json\n가드 read · 커밋")

# healthchecks.io
box(2, 44, 26, 8, "healthchecks.io", GRAY, GRAY_E, fs=8.7)
arrow((11, 44), (11, 37), rad=0)          # 메인 → hc (ping)
label(11, 40.5, "ping")
arrow((28, 47), (38, 55), rad=-0.2)       # hc → 운영자 (down alert)
label(31, 52.5, "핑 유실 시\n다운 알림")

fig.tight_layout(pad=0.4)
out = __file__.replace("\\", "/").rsplit("/", 1)[0] + "/v2_1_telegram.png"
fig.savefig(out, dpi=160)
print("wrote", out)
