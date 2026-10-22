"""소식 분류 프롬프트 시험 — 정답표(1~59번) 대비 일치율.

python -I -X utf8 notice_cat_exp.py build                  # data/ → gold.json(네트워크 없음)
python -I -X utf8 notice_cat_exp.py dry A|B                # 프롬프트 크기 · 예상 토큰만
python -I -X utf8 notice_cat_exp.py run A|B BATCH_NO X.env # 묶음 하나만 실제 호출(오류 · 429면 STOP 파일 남기고 멈춤)
python -I -X utf8 notice_cat_exp.py score A|B              # 이 폴더의 out_*.json 채점
"""
import glob, json, os, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = sys.argv[-1] if sys.argv[-1].endswith(".env") else None   # run 은 마지막 인자로 .env 경로(GROQ_API_KEY)
CATS = ["live", "event", "goods", "broadcast"]
BATCH = 9
BUDGET = 20000          # 3차(10-24~) 상한 — A안 4묶음 ≈ 13.5k. (10-23: 1차 약 12k + 2차 26,832)
# 호출은 묶음 하나씩, 사이 75초 이상(분당 한도 TPM 8,000 — 1차에 연달아 보내 429)

# 복수 분류 맞춤(2026-10-23 운영자 확정): 공연 굿즈 = live+goods, CD 발매 기념 행사 = event+goods
MULTI = {11: ["live", "goods"], 22: ["live", "goods"], 23: ["live", "goods"],
         14: ["event", "goods"],
         # 사인회 모습 생배신(「サイン会の様子を生配信」) = 방송도(2026-10-23 운영자 확정, #16 · 같은 글인 #15)
         15: ["broadcast", "event", "goods"], 16: ["broadcast", "event", "goods"],
         # 공연의 유튜브 생중계 = 라이브공연 + 방송(2026-10-23 운영자 확정 — #50 은 우천으로 현장 대신 생중계한 프리 라이브 DAY2)
         50: ["broadcast", "live"],
         30: ["event", "goods"], 35: ["event", "goods"], 54: ["event", "goods"]}
DROP = {4, 5, 34}                 # 번역 실패 · 병합 오판 — 분류 문제가 아님
FORCE = {18: ["broadcast"]}       # FM802 출연 감사(라디오) — 방송 정의 추가 뒤 기타 → 방송


def build():
    data = os.path.join(HERE, "data")
    items = {i["id"]: i for i in json.load(open(os.path.join(data, "labeler_items.json"), encoding="utf-8"))}
    authors = json.load(open(os.path.join(data, "authors.json"), encoding="utf-8"))
    labels = json.load(open(os.path.join(data, "labels_2026-10-23.json"), encoding="utf-8"))
    gold = []
    for lid, d in labels.items():
        i = items[lid]
        n = i["n"]
        if n in DROP or d.get("cat") == "game":
            continue
        a = (authors.get(i["id"]) or {}).get("author")
        if a == "bang_dream_on":
            continue
        cats = FORCE.get(n) or MULTI.get(n) or ([] if d.get("cat") in (None, "etc") else [d["cat"]])
        gold.append({"n": n, "id": i["id"], "gold": sorted(cats), "title": i["title"], "body": i["body"],
                     "note": d.get("note") or ""})
    gold.sort(key=lambda g: g["n"])
    json.dump(gold, open(os.path.join(HERE, "gold.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(len(gold), Counter(c for g in gold for c in (g["gold"] or ["etc"])))


HEAD = (
    "아래는 X(트위터) 글 여러 개다. 각 글은 성우 밴드 「夢限大みゅーたいぷ」(유메미타 — 仲町あられ · 宮永ののか · 峰月律 · 藤都子 · 千石ユノ)의 "
    "공식 계정이 쓰거나 리포스트한 글이다. 글마다 그 글이 알리는 것에 해당하는 분류를 아래에서 **모두** 골라라. 없으면 빈 목록.\n"
    "- live (라이브공연): 유메미타 전체 또는 일부 멤버가 무대에 서는 공연 — 단독 · 합동 · 프리 라이브, 투어. "
    "그 공연의 티켓 판매 · 추첨 · 중지 · 변경 안내도 포함. 공연 굿즈 판매 · 통판 안내는 live 와 goods 둘 다.\n"
    "- event (오프라인행사): 공연이 아닌, 유메미타 멤버가 나오는 행사 — 사인회(인터넷 사인회 포함) · お渡し会 · 릴리즈 이벤트 · "
    "토크쇼 · 전시 · 팝업 스토어 · 콜라보 행사.\n"
    "- goods (음원·굿즈): 유메미타의 CD(싱글 · 앨범) · 음원 · 커버곡 출시(커버곡 · MV 영상 공개 포함), 굿즈 · Blu-ray · 코믹스 등 "
    "판매되는 물건과 그 예약 · 판매 · 특전 안내. 유메미타가 잡지에 실린다는 소식(雑誌掲載 · 인터뷰 · 특집 · 포스터)도 goods. "
    "공연장 · 행사장 물판, CD 발매 기념 행사(릴리즈 이벤트 · 사인회 · お渡し会)도 포함(그 공연 · 행사 분류와 함께).\n"
    "- broadcast (방송): 유메미타 멤버가 출연하는 방송 — 유튜브 생방송 · 동시 시청 · 생일 방송, 「バンドリ！TV LIVE」, 라디오, "
    "TV · 니코니코 프로그램 출연, 멤버가 나오는 행사의 생중계(「様子を生配信」). 공연의 유튜브 생중계는 live 와 broadcast 둘 다. "
    "애니메이션 「ゆめ∞みた」의 방영 · 방송 시작 · 배신 · 몰아보기 안내는 멤버가 출연하는 방송이 아니므로 broadcast 가 아니다.\n"
)
HEAD_B = ("- related: 유메미타(멤버 포함)가 전혀 나오지 않고 다른 밴드 · 다른 작품만 다루는 글이면 false, 아니면 true.\n")
TAIL = ("evidence = 판단 근거가 된 구절들 — 글에서 한 줄씩 그대로 복사(바꾸지 말 것).\n"
        "reason = 판단 이유 한국어 한 문장.\n결과는 글 번호(n)마다 하나씩. JSON 으로만 답하라.\n")


def schema(variant):
    item = {"n": {"type": "integer"},
            "cats": {"type": "array", "items": {"type": "string", "enum": CATS}},
            # (1차 400 json_validate_failed — 모델이 객체 대신 문자열을 냄) 운영 notice_timing 과 같은 문자열 목록으로
            "evidence": {"type": "array", "items": {"type": "string"}},
            "reason": {"type": "string"}}
    if variant == "B":
        item["related"] = {"type": "boolean"}
    return {"name": "notice_categories", "strict": True, "schema": {
        "type": "object", "additionalProperties": False, "required": ["results"],
        "properties": {"results": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": list(item), "properties": item}}}}}


def prompt(variant, batch):
    head = HEAD + (HEAD_B if variant == "B" else "") + TAIL
    body = "".join(f"\n--- 글 n={g['n']} ---\n{g['title']}\n{g['body']}\n" for g in batch)
    return head + body


def batches():
    gold = json.load(open(os.path.join(HERE, "gold.json"), encoding="utf-8"))
    return [gold[k:k + BATCH] for k in range(0, len(gold), BATCH)]


def used():
    tot = 0
    for f in glob.glob(os.path.join(HERE, "out_*.json")):
        tot += (json.load(open(f, encoding="utf-8")).get("usage") or {}).get("total_tokens", 0)
    return tot


def run(variant, no):
    if os.path.exists(os.path.join(HERE, "STOP")):
        sys.exit("STOP 파일 있음 — 이전에 429/오류로 멈춤")
    if used() >= BUDGET:
        sys.exit(f"예산 {BUDGET} 도달 — 멈춤")
    key = None
    for line in open(ENV, encoding="utf-8"):
        if line.startswith("GROQ_API_KEY="):
            key = line.split("=", 1)[1].strip().strip('"').strip("'")
    b = batches()[no]
    p = prompt(variant, b)
    payload = {"model": "openai/gpt-oss-120b", "messages": [{"role": "user", "content": p}], "temperature": 0,
               "reasoning_effort": "low", "max_tokens": 6000,
               "response_format": {"type": "json_schema", "json_schema": schema(variant)}}
    req = urllib.request.Request("https://api.groq.com/openai/v1/chat/completions", data=json.dumps(payload).encode(),
                                 headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                          "User-Agent": "mewtype-notice-cat-exp"})
    t0 = time.time()
    try:
        r = urllib.request.urlopen(req, timeout=120)
        hdr = {k: v for k, v in r.headers.items() if k.lower().startswith("x-ratelimit")}
        d = json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:600]
        open(os.path.join(HERE, "STOP"), "w", encoding="utf-8").write(f"{e.code} {body}")
        sys.exit(f"HTTP {e.code} — 멈춤: {body}")
    out = {"variant": variant, "batch": no, "ns": [g["n"] for g in b], "sec": round(time.time() - t0, 1),
           "usage": d.get("usage"), "ratelimit": hdr, "content": d["choices"][0]["message"]["content"]}
    json.dump(out, open(os.path.join(HERE, f"out_{variant}_{no}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"usage": out["usage"], "ratelimit": hdr, "sec": out["sec"], "cum": used()}, ensure_ascii=False))


def score(variant):
    gold = {g["n"]: g for g in json.load(open(os.path.join(HERE, "gold.json"), encoding="utf-8"))}
    pred = {}
    for f in sorted(glob.glob(os.path.join(HERE, f"out_{variant}_*.json"))):
        for r in json.loads(json.load(open(f, encoding="utf-8"))["content"])["results"]:
            pred[r["n"]] = r
    ok = 0; rows = []
    for n, g in gold.items():
        if n not in pred:
            continue
        p = sorted(set(pred[n]["cats"]))
        hit = p == g["gold"]
        ok += hit
        if not hit or (variant == "B" and not pred[n].get("related", True)):
            rows.append((n, g["gold"] or ["etc"], p or ["etc"], pred[n].get("related"), pred[n]["reason"], g["title"][:40]))
    print(f"{variant}: 완전 일치 {ok}/{len(pred)}")
    for r in rows:
        print(" #%d 정답=%s 판정=%s related=%s | %s | %s" % r)


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "build":
        build()
    elif cmd == "dry":
        for k, b in enumerate(batches()):
            p = prompt(sys.argv[2], b)
            print(k, len(b), "chars", len(p), "≈tok", int(len(p) / 1.2))
    elif cmd == "run":
        run(sys.argv[2], int(sys.argv[3]))
    elif cmd == "score":
        score(sys.argv[2])
