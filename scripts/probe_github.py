"""(v3.8.2) 실제 GitHub Contents API 동작 확인 — 임시 브랜치에서만 (운영 data 브랜치는 건드리지 않음).

확인 항목: 지연·헤더(x-ratelimit-*, etag) · 조건부 GET(304)의 한도 집계 · 쓰기 직후 읽기 일관성 ·
같은 브랜치 동시 PUT 의 409(HEAD 충돌) · 0.3초 간격 순차 PUT · 쓰기 도중 읽기(찢어진 읽기 여부).
속도 제한(403/429) 자체는 일부러 유발하지 않는다(운영 토큰 사용자의 한도를 건드리지 않도록) — 요청 약 100건, 동시 최대 8.

사용: python scripts/probe_github.py [owner/repo]   (기본 GITHUB_REPO 환경변수 → sbb2002/mewtype-scheduler-data)
인증: `gh auth token` (repo 권한). 끝나면 임시 브랜치(tower-scratch-<시각>)를 삭제한다.
"""
import base64, hashlib, json, os, subprocess, sys, threading, time, statistics
import requests

OWNER_REPO = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("GITHUB_REPO") or "sbb2002/mewtype-scheduler-data")
API = "https://api.github.com"
TOK = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True).stdout.strip()
H = {"Authorization": f"Bearer {TOK}", "Accept": "application/vnd.github+json",
     "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "tower-probe"}
BR = f"tower-scratch-{int(time.time())}"
S = requests.Session()


def blob_sha(text: str) -> str:
    b = text.encode()
    return hashlib.sha1(b"blob %d\0" % len(b) + b).hexdigest()


def put(path, text, sha=None, sess=None):
    body = {"message": f"probe {path}", "content": base64.b64encode(text.encode()).decode(), "branch": BR}
    if sha:
        body["sha"] = sha
    t0 = time.monotonic()
    r = (sess or S).put(f"{API}/repos/{OWNER_REPO}/contents/{path}", headers=H, json=body, timeout=30)
    return r, time.monotonic() - t0


def get(path, etag=None, sess=None):
    h = dict(H)
    if etag:
        h["If-None-Match"] = etag
    t0 = time.monotonic()
    r = (sess or S).get(f"{API}/repos/{OWNER_REPO}/contents/{path}", headers=h, params={"ref": BR}, timeout=30)
    return r, time.monotonic() - t0


def rl(r):
    return {k: r.headers.get(k) for k in ("x-ratelimit-limit", "x-ratelimit-remaining", "x-ratelimit-used", "x-ratelimit-resource", "retry-after") if r.headers.get(k) is not None}


out = {}
try:
    head = S.get(f"{API}/repos/{OWNER_REPO}/git/ref/heads/data", headers=H).json()["object"]["sha"]
    r = S.post(f"{API}/repos/{OWNER_REPO}/git/refs", headers=H, json={"ref": f"refs/heads/{BR}", "sha": head})
    assert r.status_code == 201, r.text
    print(f"임시 브랜치 생성: {BR}")

    # 1) 기본 지연·헤더
    r, dt = put("probe/base.json", '{"n":0}\n')
    assert r.status_code in (200, 201), r.text
    base_sha = r.json()["content"]["sha"]
    out["put_first_ms"] = round(dt * 1000)
    g, dg = get("probe/base.json")
    etag = g.headers.get("etag")
    print(f"[1] PUT {r.status_code} {dt*1000:.0f}ms · GET {g.status_code} {dg*1000:.0f}ms · etag={etag} · 헤더={rl(g)}")

    # 2) 조건부 요청(304)이 한도에 세어지는가
    before = int(S.get(f"{API}/rate_limit", headers=H).json()["resources"]["core"]["used"])
    r200, _ = get("probe/base.json")                       # 일반 GET (1점 소모 예상)
    mid = int(S.get(f"{API}/rate_limit", headers=H).json()["resources"]["core"]["used"])
    r304, _ = get("probe/base.json", etag=etag)            # 조건부 GET (304 → 소모 없음 예상)
    after = int(S.get(f"{API}/rate_limit", headers=H).json()["resources"]["core"]["used"])
    print(f"[2] 일반 GET {r200.status_code} → used {before}→{mid} (+{mid-before}) · 조건부 GET {r304.status_code} → used {mid}→{after} (+{after-mid}) · 304 헤더={rl(r304)}")
    out["etag_304_counted"] = (after - mid)

    # 3) 쓰기 직후 읽기 일관성 (read-after-write)
    stale = 0
    sha = base_sha
    for i in range(12):
        txt = json.dumps({"n": i + 1}) + "\n"
        rp, _ = put("probe/base.json", txt, sha=sha)
        assert rp.status_code in (200, 201), rp.text
        sha = rp.json()["content"]["sha"]
        rg, _ = get("probe/base.json")
        if rg.json()["sha"] != sha:
            stale += 1
    print(f"[3] 쓰기 직후 즉시 읽기 12회 중 옛 값 {stale}회")
    out["read_after_write_stale"] = stale

    # 4) 동시 PUT (서로 다른 새 파일, 같은 브랜치) — HEAD 충돌 409 가 실제로 나는가
    def burst(n, tag):
        res = []
        gate = threading.Barrier(n)

        def w(i):
            s = requests.Session()
            gate.wait()
            r, dt = put(f"probe/{tag}_{i}.json", json.dumps({"i": i}) + "\n", sess=s)
            res.append((r.status_code, round(dt * 1000), r.text[:70] if r.status_code >= 400 else "", rl(r) if r.status_code >= 400 else {}))
        ths = [threading.Thread(target=w, args=(i,)) for i in range(n)]
        [t.start() for t in ths]; [t.join() for t in ths]
        return res

    for n, tag in ((3, "c3"), (5, "c5"), (5, "c5b"), (8, "c8")):
        res = burst(n, tag)
        codes = sorted(c for c, *_ in res)
        print(f"[4] 동시 PUT {n}개 → 상태 {codes}  " + (f"실패 예시 {[x for x in res if x[0] >= 400][:2]}" if any(c >= 400 for c in codes) else ""))
        out[f"concurrent_{tag}"] = codes
        time.sleep(1.5)

    # 5) 순차 PUT — 0.3s 간격이면 오류 없는가, 실제 지연
    lat, codes = [], []
    for i in range(10):
        t_gap = time.monotonic()
        r, dt = put(f"probe/seq_{i}.json", json.dumps({"i": i}) + "\n")
        lat.append(dt * 1000); codes.append(r.status_code)
        time.sleep(0.3)
    print(f"[5] 순차 PUT 10회(0.3s 간격) 상태 {sorted(set(codes))} · 지연 중앙 {statistics.median(lat):.0f}ms · 최대 {max(lat):.0f}ms")
    out["seq_put_median_ms"] = round(statistics.median(lat))

    # 6) GET 지연
    glat = []
    for i in range(10):
        r, dt = get("probe/base.json"); glat.append(dt * 1000)
    print(f"[6] GET 10회 지연 중앙 {statistics.median(glat):.0f}ms · 최대 {max(glat):.0f}ms")
    out["get_median_ms"] = round(statistics.median(glat))

    # 7) 쓰기 도중 읽기 — 응답이 일관(내용↔sha 짝)한가, 옛/새 어느 쪽이든
    cur_r, _ = get("probe/base.json")
    cur_sha = cur_r.json()["sha"]
    seen, torn = set(), 0
    stop = threading.Event()

    def reader():
        global torn
        s = requests.Session()
        while not stop.is_set():
            rg, _ = get("probe/base.json", sess=s)
            if rg.status_code != 200:
                continue
            j = rg.json()
            text = base64.b64decode(j["content"]).decode()
            seen.add(j["sha"])
            if blob_sha(text) != j["sha"]:
                torn += 1
    rt = threading.Thread(target=reader); rt.start()
    sha = cur_sha
    for i in range(6):
        rp, _ = put("probe/base.json", json.dumps({"w": i}) + "\n", sha=sha)
        if rp.status_code in (200, 201):
            sha = rp.json()["content"]["sha"]
    time.sleep(0.5); stop.set(); rt.join()
    print(f"[7] 쓰기 6회 도중 읽기: 서로 다른 버전 {len(seen)}종 관측, 내용↔sha 불일치(찢어진 읽기) {torn}건")
    out["torn_reads"] = torn
finally:
    r = S.delete(f"{API}/repos/{OWNER_REPO}/git/refs/heads/{BR}", headers=H)
    print(f"임시 브랜치 삭제: {r.status_code}")
    rem = S.get(f"{API}/rate_limit", headers=H).json()["resources"]["core"]
    print(f"남은 한도: {rem['remaining']}/{rem['limit']}")
print(json.dumps(out, ensure_ascii=False))
