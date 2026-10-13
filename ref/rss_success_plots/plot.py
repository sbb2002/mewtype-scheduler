"""배포판 RSS 요청 성공률 시간대별 플롯. 입력 hourly.csv (Cloud Logging 집계) → png 2장.
성공 = `Failed to fetch RSS` 경고가 없는 요청. 개인 5채널(그룹 채널 제외) / 곡 토픽 채널. 10-04 이후만(그룹 채널을 RSS 에서 뺀 배포 이후)."""
import csv
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

matplotlib.rcParams["font.family"] = "Malgun Gothic"
matplotlib.rcParams["axes.unicode_minus"] = False
HERE = Path(__file__).parent
SINCE = "2026-10-04"
rows = [r for r in csv.DictReader(open(HERE / "hourly.csv", encoding="utf-8")) if r["date_kst"] >= SINCE]
H = range(24)
dates = sorted({r["date_kst"] for r in rows})
heat = np.full((len(dates), 24), np.nan)      # 개인 채널 날짜 × 시각 성공률
mem_d = [[] for _ in H]                       # 시각별 날짜 값(개인 채널)
song_d = [[] for _ in H]                      # 시각별 날짜 값(곡 토픽)
tk = 0; sa_tot = 0
for r in rows:
    h = int(r["hour_kst"]); t_ = int(r["ticks"]); sa_ = int(r["song_attempts"])
    if t_:
        v = 100 * (1 - int(r["member_fetch_fail(5ch)"]) / (5 * t_))
        heat[dates.index(r["date_kst"]), h] = v; mem_d[h].append(v); tk += t_
    if sa_:
        song_d[h].append(100 * (1 - int(r["song_fail"]) / sa_)); sa_tot += sa_


def stat(lists):
    """시각별 날짜 값의 중앙값과 사분위(Q1·Q3). 에러바 = 중앙값에서 Q1·Q3 까지."""
    med = np.array([np.median(x) if x else np.nan for x in lists])
    q1 = np.array([np.percentile(x, 25) if x else np.nan for x in lists])
    q3 = np.array([np.percentile(x, 75) if x else np.nan for x in lists])
    return med, np.vstack([med - q1, q3 - med])


mem, mem_e = stat(mem_d)
song, song_e = stat(song_d)
n_mem = max(len(x) for x in mem_d); n_song = max(len(x) for x in song_d)

fig, ax = plt.subplots(figsize=(11, 5.5))
ax.errorbar(list(H), mem, yerr=mem_e, fmt="o-", capsize=3, color="#d94f4f", alpha=.95,
            label=f"예고(틱) — 개인 채널 5개 합산 (최대 {n_mem}일, 요청 {5*tk:,}회)")
ax.errorbar(np.array(list(H)) + .12, song, yerr=song_e, fmt="s--", capsize=3, color="#3b7dd8", alpha=.95,
            label=f"음원 — 곡 토픽 채널 (최대 {n_song}일, 요청 {sa_tot:,}회, 10-08~)")
ax.axvspan(7.5, 16.5, color="#f2c94c", alpha=.15, label="실패 집중 구간(08~16시)")
ax.set_xticks(list(H)); ax.set_xlabel("시각 (KST)"); ax.set_ylabel("RSS 요청 성공률 (%) — 날짜별 값의 분포"); ax.set_ylim(-3, 105)
ax.set_title(f"배포판 RSS 요청 성공률 — 시간대별 중앙값 · 사분위(Q1~Q3, 날짜 간), {dates[0]} ~ {dates[-1]}")
ax.grid(alpha=.3); ax.legend(loc="lower left")
fig.tight_layout(); fig.savefig(HERE / "rss_success_by_hour.png", dpi=140); plt.close(fig)

fig, ax = plt.subplots(figsize=(11, 7))
im = ax.imshow(heat, aspect="auto", cmap="RdYlGn", vmin=0, vmax=100)
ax.set_xticks(range(24)); ax.set_xticklabels(range(24)); ax.set_yticks(range(len(dates))); ax.set_yticklabels([d[5:] for d in dates])
ax.set_xlabel("시각 (KST)"); ax.set_ylabel("날짜"); ax.set_title("개인 채널 RSS 요청 성공률(%) — 날짜 × 시각 (회색 = 틱 없음)")
fig.colorbar(im, label="성공률 (%)"); fig.tight_layout(); fig.savefig(HERE / "rss_success_heatmap.png", dpi=140); plt.close(fig)
print("저장:", HERE)
