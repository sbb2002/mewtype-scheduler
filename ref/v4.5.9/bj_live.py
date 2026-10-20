# v4.5.9 banner_judge 새 프롬프트 실측 — 지난 게임 계정 글 + JR 콜라보 (출력 = 판정만)
import json, os, sys
sys_ = __import__("sys"); sys_.stdout.reconfigure(encoding="utf-8")
for line in open(r"C:/Users/User/Documents/pyworks/mewtype-scheduler/.env", encoding="utf-8"):
    line = line.strip()
    if line.startswith("GROQ") and "=" in line:
        k, v = line.split("=", 1); os.environ[k.strip()] = v.strip().strip('"').strip("'")
sys.path.insert(0, r"C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/hotfix-game-collab-notice")
from src.backend.llm import LLMClient
c = LLMClient(os.environ["GROQ_API_KEY"])
cases = json.load(open("bj_cases.json", encoding="utf-8"))
want = {"推し旅": "notice", "東京メトロ": "notice", "トークショー": "notice", "サイン会": "notice", "入場者プレゼント": "notice",
        "サイドスロー」  ぜひ": "upsert", "差し込む光": "upsert", "メンテナンス実施のお知らせ】 イベント": "none", "特別ログインボーナス🛸": "none",
        "生配信！ 「#バンドリTVLIVE 2026」#336  配信内にて、": "none", "夢我夢中": "none", "だんらんTV": "none", "Shake Your 魂, Baby!!」  ぜひ": "upsert"}
pick = []
for k, w in want.items():
    hit = next((x for x in cases if k in x["raw"].replace("\n", " ")), None)
    if hit: pick.append((k, w, hit))
ok = 0
for k, w, x in pick:
    j = c.banner_judge(x["raw"], x["ts"][:16].replace("T", " "), [])
    got = j and j["action"]
    ok += got == w
    print(f"{'OK ' if got == w else 'XX '} 기대={w:7} 결과={got!s:7} kind={(j or {}).get('post_kind')} | {k} | {(j or {}).get('reason','')[:70]}")
print(f"{ok}/{len(pick)}")
