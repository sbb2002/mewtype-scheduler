import json, os, sys
sys.stdout.reconfigure(encoding="utf-8")
for line in open(r"C:/Users/User/Documents/pyworks/mewtype-scheduler/.env", encoding="utf-8"):
    line = line.strip()
    if line.startswith("GROQ") and "=" in line:
        k, v = line.split("=", 1); os.environ[k.strip()] = v.strip().strip('"').strip("'")
sys.path.insert(0, r"C:/Users/User/Documents/pyworks/mewtype-scheduler-worktrees/v4/hotfix-game-collab-notice")
from src.backend.llm import LLMClient
c = LLMClient(os.environ["GROQ_API_KEY"])
for x in json.load(open("bj_cases.json", encoding="utf-8")):
    old = "upsert" if ("추가" in x["summary"] or "갱신" in x["summary"]) else "none"
    j = c.banner_judge(x["raw"], x["ts"][:16].replace("T", " "), [])
    new = j and j["action"]
    mark = "  " if new == old else "≠ "
    print(f"{mark}{old:6}→{new!s:7} {(j or {}).get('post_kind')!s:11} | {x['raw'][:50].replace(chr(10),' ')}")
