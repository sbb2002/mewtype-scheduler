import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
for line in open(r"C:/Users/User/Documents/pyworks/mewtype-scheduler/.env", encoding="utf-8"):
    line = line.strip()
    if line.startswith("GROQ") and "=" in line:
        k, v = line.split("=", 1); os.environ[k.strip()] = v.strip().strip('"').strip("'")
sys.path.insert(0, r"C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/hotfix-game-collab-notice")
from src.backend.llm import LLMClient
c = LLMClient(os.environ["GROQ_API_KEY"])
cases = json.load(open("bj_cases.json", encoding="utf-8"))
want = [("millsage初イベント", "game_event"), ("一家Dumb Rock!初イベント", "game_event"), ("13th☆LIVE", "game_notice"),
        ("📢開催決定！", "game_notice"), ("公開記念 特別ログインボーナス🌙", "game_notice"), ("推し旅", "outside"),
        ("東京メトロ", "outside"), ("入場者プレゼント", "outside"), ("サイン会", "outside"), ("遊び方", "game_event"), ("だんらんTV", "broadcast")]
bad = 0
for rnd in range(3):
    for k, w in want:
        x = next(x for x in cases if k in x["raw"])
        j = c.banner_judge(x["raw"], x["ts"][:16].replace("T", " "), []) or {}
        if j.get("post_kind") != w:
            bad += 1; print(f"XX r{rnd} {k}: 기대 {w} 결과 {j.get('post_kind')}/{j.get('action')} | {j.get('reason','')[:60]}")
print("어긋남", bad, "/", 3 * len(want))
