"""v2_3_x_relay.png 생성 스크립트 — v2.3 X 예고 릴레이 → scheduled 단계.

    python docs/plan/gen_x_relay.py
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

fig, ax = plt.subplots(figsize=(10.8, 7.2), dpi=160)
ax.set_xlim(0, 108)
ax.set_ylim(0, 72)
ax.axis("off")


def box(x, y, w, h, text, fc, ec, *, fs=8.6):
    ax.add_patch(FancyBboxPatch((x, y), w, h,
                boxstyle="round,pad=0.6,rounding_size=1.4", fc=fc, ec=ec, lw=1.6))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center",
            fontsize=fs, weight="bold", color=INK)


def arrow(p0, p1, *, rad=0.0, ls="-", lw=1.6):
    ax.add_patch(FancyArrowPatch(p0, p1, connectionstyle=f"arc3,rad={rad}",
                arrowstyle="-|>", mutation_scale=15, lw=lw, ls=ls, color="#3a3a3a"))


def label(x, y, t, *, fs=8.0):
    ax.text(x, y, t, ha="center", va="center", fontsize=fs, color="#4a4a4a")


ax.text(54, 69, "v2.3 — X 예고 릴레이 → scheduled 단계",
        ha="center", va="center", fontsize=15, weight="bold", color=INK)

# 폰
box(8, 55, 44, 11,
    "S23 · Automate\n삼성 브라우저 웹푸시 알림\n→ Expression true?  (스케줄 헤더 매칭 시만)\n→ HTTP POST",
    BLUE, BLUE_E, fs=8.2)

# telegram 서비스 /ingest
box(8, 36, 44, 12,
    "mewtype-telegram  (공개)\nPOST /ingest  ·  X-Ingest-Secret 검증\nxrelay.parse_bdp_schedule\n→ merge_scheduled (replace-by-date)",
    GREEN, GREEN_E, fs=8.0)
arrow((30, 55), (30, 48), rad=0)
label(30, 51.6, "text = 알림 본문\n(android.bigText)")

# DRY-RUN 노트
box(58, 38, 44, 9,
    "INGEST_DRY_RUN=1\n→ schedule.json 안 씀\n원문·파싱결과만 운영자 DM",
    GRAY, GRAY_E, fs=8.0)
arrow((58, 42.5), (52, 42.5), rad=0, ls="--")

# 운영자 DM (계약 G)
box(58, 54, 44, 8, "운영자 Telegram DM\n계약 G — 반영 결과 / 경고", BLUE, BLUE_E, fs=8.2)
arrow((45, 48), (66, 54), rad=-0.15)
label(60, 51.5, "sendMessage")

# data 브랜치 schedule.json
box(14, 18, 50, 10,
    "GitHub  data 브랜치  ·  schedule.json\nbroadcasts[]  에  status:\"scheduled\"  행\n(video_id 없음 · sched_id 키)",
    ORANGE, ORANGE_E, fs=8.2)
arrow((30, 36), (34, 28), rad=0.12)
label(23, 32.5, "커밋\n(sha 검사+재시도)")

# 정기 tick / reconcile
box(66, 14, 40, 15,
    "정기  /tick  (Cloud Scheduler)\nreconcile.build_schedule\n· 같은 채널 실물 upcoming/live\n  가 ±4h 안 → supersede(제거)\n· expires_at(start+3h) 도달 → 제거\n· 그 외 → 이관",
    GREEN, GREEN_E, fs=7.8)
arrow((66, 22), (64, 22), rad=0)
label(65, 24.2, "보존/정리")

# 프론트
box(14, 3, 50, 9,
    "프론트 (Vercel) · 75s 폴링\nv1 은 scheduled 행 무시(롤백 안전)\n.card--scheduled 렌더는 후속",
    BLUE, BLUE_E, fs=8.0)
arrow((39, 18), (39, 12), rad=0)
label(39, 15, "raw fetch")

fig.tight_layout(pad=0.4)
out = __file__.replace("\\", "/").rsplit("/", 1)[0] + "/v2_3_x_relay.png"
fig.savefig(out, dpi=160)
print("wrote", out)
