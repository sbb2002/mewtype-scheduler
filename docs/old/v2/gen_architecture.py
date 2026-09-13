"""v1_impro_architecture.png 재생성 스크립트.

v2.0 확정 아키텍처(docs/plan/v1_impro_final.md)를 그림으로. 백엔드 compute 를
GitHub Actions → Cloud Run 으로 교체 반영.

    python docs/plan/gen_architecture.py
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch, Rectangle

# ── 한글 폰트 ──
for _name in ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR"):
    if any(f.name == _name for f in fm.fontManager.ttflist):
        plt.rcParams["font.family"] = _name
        break
plt.rcParams["axes.unicode_minus"] = False

GREEN = "#e3f0e0"
GREEN_E = "#7fae7a"
PURPLE = "#e6e0f0"
PURPLE_E = "#9a86c8"
PINK = "#f6dfe3"
PINK_E = "#c98a94"
ORANGE = "#fdeccd"
ORANGE_E = "#d8a24a"
INK = "#2b2b2b"

fig, ax = plt.subplots(figsize=(10.3, 6.7), dpi=160)
ax.set_xlim(0, 103)
ax.set_ylim(0, 67)
ax.axis("off")


def box(x, y, w, h, text, fc, ec, *, fs=9, bold=True):
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0.6,rounding_size=1.4",
            fc=fc, ec=ec, lw=1.6,
        )
    )
    ax.text(
        x + w / 2, y + h / 2, text,
        ha="center", va="center", fontsize=fs,
        weight="bold" if bold else "normal", color=INK,
    )


def group(x, y, w, h, label):
    ax.add_patch(
        Rectangle((x, y), w, h, fill=False, ec="#3a3a3a", lw=1.4, ls=(0, (6, 4)))
    )
    ax.text(x + 2.4, y + h - 3.2, label, fontsize=11, weight="bold", color=INK)


def arrow(p0, p1, *, rad=0.0, lw=1.6, ls="-"):
    ax.add_patch(
        FancyArrowPatch(
            p0, p1,
            connectionstyle=f"arc3,rad={rad}",
            arrowstyle="-|>", mutation_scale=16,
            lw=lw, ls=ls, color="#3a3a3a",
        )
    )


def label(x, y, text, *, fs=8.5):
    ax.text(x, y, text, ha="center", va="center", fontsize=fs, color="#4a4a4a")


# ── 제목 ──
ax.text(51.5, 64.5, "v1_impro 최종 상호작용 아키텍처",
        ha="center", va="center", fontsize=15, weight="bold", color=INK)

# ── Backend 그룹 ──
group(3, 27, 62, 33, "Backend  (Role)")
box(5.5, 46.5, 27, 10.5,
    "정기 트리거\n(Cloud Scheduler ×1)\n06:00 baseline · 3h 안전망", GREEN, GREEN_E, fs=8.5)
box(5.5, 30.5, 27, 10.5,
    "Cloud Tasks\n(방송별 일회성\nwake 큐)", GREEN, GREEN_E, fs=8.5)
box(38, 34.5, 24, 19,
    "Cloud Run\n(수집 · 판정 ·\npending.json ·\nwake enqueue)", GREEN, GREEN_E, fs=9)

arrow((32.5, 51), (38, 47), rad=-0.15)
label(35.6, 53.2, "정기 트리거")
arrow((32.5, 36.5), (38, 40.5), rad=0.18)
arrow((38, 38.5), (32.5, 34.5), rad=0.18)
label(35.3, 30.6, "enqueue / wake")

# ── Frontend 그룹 ──
group(71, 27, 29, 33, "Frontend  (Role)")
box(73.5, 46, 24, 10, "Vercel\n(정적 assets 호스팅)", PURPLE, PURPLE_E, fs=8.5)
box(73.5, 31, 24, 11, "브라우저 프론트엔드\n(유저가 보는 화면)", PURPLE, PURPLE_E, fs=8.5)
arrow((85.5, 46), (85.5, 42), rad=0)
label(90.5, 44, "정적 서빙")

# ── 하단: 외부 API / data 브랜치 ──
box(20, 3, 33, 15, "외부 API — YouTube (5채널)", PINK, PINK_E, fs=9)
for i, ch in enumerate("AYNRM"):
    cx = 25.5 + i * 5.4
    ax.add_patch(plt.Circle((cx, 7.2), 1.7, fc="white", ec=PINK_E, lw=1.3))
    ax.text(cx, 7.2, ch, ha="center", va="center", fontsize=8, color=INK)

box(56, 4.5, 39, 12,
    "GitHub `data` 브랜치\nschedule · archive · pending.json", ORANGE, ORANGE_E, fs=9)

# ── 하단 연결선 ──
arrow((44, 34.5), (40, 18), rad=0.12)
arrow((40, 18), (44, 34.5), rad=0.12)
label(24.5, 24.5, "poll / 상태 반환\n(videos.list · RSS)")

arrow((54, 34.5), (68, 16.5), rad=-0.12)
label(66, 25, "commit\n(변경 시 · Contents API)")

arrow((80, 16.5), (82, 31), rad=-0.12)
label(90.5, 24, "raw fetch\n(75s 폴링)")

fig.tight_layout(pad=0.4)
out = __file__.rsplit("/", 1)[0].rsplit("\\", 1)[0] + "/v1_impro_architecture.png"
fig.savefig(out, dpi=160)
print("wrote", out)
