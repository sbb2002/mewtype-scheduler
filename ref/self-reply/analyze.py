"""profiles.json → 자기 답글 목록 · 간격 · 원글별 개수. 결과는 report.txt (utf-8)."""
import json, datetime as D, collections, statistics, sys
from pathlib import Path

P = json.load(open(sys.argv[1], encoding="utf-8"))
out = open(sys.argv[2], "w", encoding="utf-8")
sf = lambda i: ((int(i) >> 22) + 1288834974657) / 1000
KST = D.timezone(D.timedelta(hours=9))
kst = lambda t: D.datetime.fromtimestamp(t, KST).strftime("%Y-%m-%d %H:%M:%S")
w = lambda *a: print(*a, file=out)

all_gaps_parent, all_gaps_root, per_root_all, rows_all = [], [], [], []
for h, rows in P.items():
    own = {r["id"]: r for r in rows if not r["repost"] and (r["author"] or "").lower() == h}
    selfr = sorted([r for r in own.values() if (r["reply_to"] or "").lower() == h], key=lambda r: sf(r["id"]))
    others = sum(1 for r in own.values() if r["reply_to"] and (r["reply_to"] or "").lower() != h)
    ts = [sf(i) for i in own]
    w(f"== {h}: 본인 글 {len(own)} ({kst(min(ts))} ~ {kst(max(ts))}), 자기 답글 {len(selfr)}, 남에게 단 답글 {others}")
    # 뿌리 원글 찾기 (자기 답글 사슬을 위로)
    def root(r):
        cur = r
        while cur["reply_to_status"] and cur["reply_to_status"] in own and (own[cur["reply_to_status"]]["reply_to"] or "").lower() == h:
            cur = own[cur["reply_to_status"]]
        return cur["reply_to_status"] or cur["id"]
    by_root = collections.defaultdict(list)
    for r in selfr:
        p = r["reply_to_status"]
        rt = root(r)
        g_par = (sf(r["id"]) - sf(p)) / 60
        g_root = (sf(r["id"]) - sf(rt)) / 60
        by_root[rt].append(r)
        all_gaps_parent.append(g_par); all_gaps_root.append(g_root)
        rows_all.append((h, r, p, rt, g_par, g_root))
        w(f"  {kst(sf(r['id']))}  바로 위 {kst(sf(p))} (+{g_par:.1f}분)  뿌리 {kst(sf(rt))} (+{g_root:.1f}분)  "
          f"{'뿌리 목록에 있음' if rt in own else '뿌리 목록 밖'}  {r['text'][:50]!r}")
    for rt, lst in by_root.items():
        per_root_all.append((h, rt, len(lst)))
    w(f"  원글(뿌리) 수 {len(by_root)}, 원글당 답글 수 분포 {dict(collections.Counter(len(v) for v in by_root.values()))}")
    w()

def dist(gs, name):
    gs = sorted(gs)
    bins = [(0, 1), (1, 2), (2, 5), (5, 15), (15, 60), (60, 360), (360, 1440), (1440, 10**9)]
    w(f"[{name}] n={len(gs)} 중앙값 {statistics.median(gs):.1f}분 최소 {gs[0]:.1f} 최대 {gs[-1]:.1f}")
    for a, b in bins:
        c = sum(1 for g in gs if a <= g < b)
        w(f"   {a}~{b if b < 10**9 else '∞'}분: {c}")

dist(all_gaps_parent, "바로 위 글과의 간격")
dist(all_gaps_root, "뿌리 원글과의 간격")
w("원글당 자기 답글 수:", dict(sorted(collections.Counter(n for _, _, n in per_root_all).items())))
w("원글 수 합계:", len(per_root_all), "자기 답글 합계:", sum(n for _, _, n in per_root_all))
