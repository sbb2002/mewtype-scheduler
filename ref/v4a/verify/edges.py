"""trace.json → 흐름도(v4a_flow.html) 노드 이동으로 변환. 시나리오별 순서를 출력하고 edges.json 저장.

노드 이름은 흐름도의 것을 쓴다: up(업스트림) op(운영자) tg(Telegram) adm(관리 페이지) sch(정기 잡)
ctrl(접수 서비스) qa(적용 큐) be(쓰기 서비스) qe(가공 큐) data ops mon yt ytdlp groq vx browser
로컬 추가: raw(원문 보존 — 흐름도에 없음, D19)
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
T = json.loads((HERE / "trace.json").read_text(encoding="utf-8"))

ACT = {"intake": "ctrl", "writer": "be", "enrich": "ctrl"}   # 가공 큐 작업은 접수 서비스 /enrich 에서 실행(흐름도)
SVC = {"youtube": "yt", "groq": "groq", "vxtwitter": "vx", "yt-dlp": "ytdlp"}


def edge(e):
    a, st = e["actor"], e["step"]
    if st == "http-in":
        p = e["path"]
        if p == "/ingest":
            return ("E", ["up", "ctrl"], "업스트림 → /ingest")
        if p == "/telegram":
            return ("E", ["op", "tg", "ctrl"], "텔레그램 명령")
        if p.startswith("/admin"):
            return ("E", ["adm", "ctrl"], f"관리 페이지 {p.replace('/admin', '') or '/'}")
        if p.startswith("/monitor-live"):
            return ("F", ["browser", "ctrl"], "웹 모니터")
        if p.startswith("/data") or p == "/":
            return ("F", ["browser", "ctrl"], f"프론트 {p}")
        return None
    if st == "external":
        return ("X", [ACT[a], SVC[e["svc"]]], f"{e['svc']} {e['call']}")
    if st == "enqueue":
        q = "qa" if e["queue"] == "apply" else "qe"
        tgt = f"{e['kind']}" + (f"({e.get('scope')})" if e.get("scope") else "")
        when = " · 예약" if e.get("run_at") and e.get("name") else ""
        return ("O", [ACT[a], q], f"적재 {tgt}{when}")
    if st == "job-start":
        return ("O", ["qa" if e["queue"] == "apply" else "qe", "be" if e["queue"] == "apply" else "ctrl"],
                f"실행 {e['kind']}" + (f"({e.get('scope')})" if e.get("scope") else ""))
    if st == "job-fail":
        return ("O", ["be"], f"실패 {e['kind']} (시도 실패)")
    if st == "write":
        return ("S", [ACT[a], e["branch"] if e["branch"] in ("data", "ops", "monitoring", "raw") else e["branch"]],
                f"쓰기 {e['branch']}:{e['path']}")
    if st == "dm":
        return ("X", [ACT[a], "tg", "op"], "DM " + e["text"][:40])
    if st == "VIOLATION":
        return ("!", [ACT[a]], e["what"])
    return None


out = {}
for e in T:
    ed = edge(e)
    if not ed:
        continue
    k, path, label = ed
    path = ["mon" if p == "monitoring" else p for p in path]
    out.setdefault(e["scenario"], []).append({"i": e["i"], "t": e["t"], "kind": k, "path": path,
                                              "label": label, "thread": e["thread"]})

(HERE / "edges.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
if __name__ == "__main__":
    want = sys.argv[1] if len(sys.argv) > 1 else None
    for sc, evs in out.items():
        if want and want not in sc:
            continue
        print(f"\n## {sc}  ({len(evs)} 단계)")
        prev = None
        for ev in evs:
            key = (ev["kind"], tuple(ev["path"]), ev["label"])
            if key == prev:
                continue
            prev = key
            print(f"  {ev['kind']} {'→'.join(ev['path']):<22} {ev['label']}  [{ev['thread']}]")
