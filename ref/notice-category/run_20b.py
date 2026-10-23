"""(10-23) gpt-oss-20b 로 2 · 3 · 4 · 5차를 두 데이터셋에 — 차례로, 누적 상한을 넘으면 멈춤.

20b = 운영 예비 모델(120b 가 막히면 씀) — 일일 토큰 20만 중 폴백용 3만 이상을 남긴다(운영자 10-23) → 이 시험 누적 상한 15만.
분당 한도는 notice_cat_exp.runall 이 지킨다(요청 사이 75초 이상 · 분당 토큰 잔량 부족 시 더 대기 · 오류 · 429 면 STOP).
python -I -X utf8 -B run_20b.py <GROQ_API_KEY 가 든 .env.local>
"""
import glob, json, os, subprocess, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = sys.argv[1]
CAP = 150_000
JOBS = [("hrun", "5"), ("hrun", "2"), ("hrun", "4"), ("hrun", "3"),      # 검증 세트(판단에 더 중요) 먼저 — 5차는 run5 2
        ("d1run", "5"), ("d1run", "2"), ("d1run", "4"), ("d1run", "3")]   # 1차 정답표 — 5차는 run5 1


def used():
    tot = 0
    for f in glob.glob(os.path.join(HERE, "holdout_20b", "*", "out_*.json")) + glob.glob(os.path.join(HERE, "round*_20b", "out_*.json")):
        tot += (json.load(open(f, encoding="utf-8")).get("usage") or {}).get("total_tokens", 0)
    return tot


env = dict(os.environ, EXP_MODEL="openai/gpt-oss-20b", PYTHONIOENCODING="utf-8")
for cmd, r in JOBS:
    if used() > CAP - 20_000:          # 한 회차 ≈ 1.2만 ~ 1.8만 — 다음 회차가 상한을 넘을 수 있으면 멈춤
        print(f"누적 {used()} — 상한 {CAP} 근처라 멈춤(폴백용 여유)", flush=True)
        break
    if r == "5":
        args = ["run5", "2" if cmd == "hrun" else "1"]
    else:
        args = [cmd, r]
    print(f"== {' '.join(args)} (누적 {used()})", flush=True)
    p = subprocess.run([sys.executable, "-I", "-X", "utf8", "-B", os.path.join(HERE, "notice_cat_exp.py"), *args, ENV], env=env)
    if p.returncode != 0:
        print(f"멈춤 — {' '.join(args)} 종료 코드 {p.returncode}", flush=True)
        break
    time.sleep(80)                     # 회차 사이 분당 한도 여유
print(f"끝 — 누적 {used()}", flush=True)
