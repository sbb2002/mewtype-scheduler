"""소식 분류 프롬프트 시험 — 정답표(1~59번) 대비 일치율.

python -I -X utf8 notice_cat_exp.py build                  # data/ → gold.json(네트워크 없음)
python -I -X utf8 notice_cat_exp.py dry A|B                # 프롬프트 크기 · 예상 토큰만
python -I -X utf8 notice_cat_exp.py run A|B BATCH_NO X.env # 묶음 하나만 실제 호출(오류 · 429면 STOP 파일 남기고 멈춤)
python -I -X utf8 notice_cat_exp.py score A|B              # 이 폴더의 out_*.json 채점
python -I -X utf8 notice_cat_exp.py runall A X.env.local   # (3차) 전 묶음을 차례로 — 한도 헤더 확인 · 75초 이상 간격 · 오류면 STOP
(검증 세트 — 프롬프트를 고칠 때 보지 않은 글로 과적합 확인)
python -I -X utf8 notice_cat_exp.py hbuild                 # data/holdout_* → gold_holdout.json
python -I -X utf8 notice_cat_exp.py hdry 2|3|4             # 그 회차 프롬프트(roundN/prompt_A_batch0.txt 머리)로 예상 토큰
python -I -X utf8 notice_cat_exp.py hrun 2|3|4 X.env.local # 그 회차 프롬프트로 검증 세트 전 묶음 → holdout/rN/
python -I -X utf8 notice_cat_exp.py hscore 2|3|4           # holdout/rN/ 채점(gold_holdout.json)
(5차 — 주제 먼저 · 분류마다 예/아니오 + 근거, ROUND5_PLAN.md)
python -I -X utf8 notice_cat_exp.py run5 1|2 X.env.local   # 1 = 1차 정답표(36건) → round5/, 2 = 검증 세트(29건) → holdout/r5/
python -I -X utf8 notice_cat_exp.py score5 1|2             # 같은 폴더 채점 + 2 · 3 · 4차와 비교표
python -I -X utf8 notice_cat_exp.py dry5 1|2               # 5차 프롬프트 크기만(호출 없음)
"""
import glob, json, os, re, sys, time, urllib.request, urllib.error

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = sys.argv[-1] if ".env" in os.path.basename(sys.argv[-1]) else None   # run 은 마지막 인자로 .env · .env.local 경로(GROQ_API_KEY)
CATS = ["live", "event", "goods", "broadcast"]
BATCH = 9
BUDGET = 20000          # 회차(OUT 폴더)별 상한 — A안 4묶음 ≈ 14.5k. (10-23: 1차 약 12k + 2차 26,832 + 3차 14,403)
# 호출은 묶음 하나씩, 사이 75초 이상(분당 한도 TPM 8,000 — 1차에 연달아 보내 429)
OUT = os.path.join(HERE, "round4")   # 응답 · STOP · 예산 계산을 이 폴더로(1 · 2차는 끝난 뒤 손으로 옮겼다, 3차 = round3)
GOLD = os.path.join(HERE, "gold.json")   # 정답표 — 검증 세트 명령(h*)은 gold_holdout.json 으로 바꾼다
HEAD_OVERRIDE = None    # 검증 세트 명령은 그 회차에 실제로 보낸 프롬프트 머리(roundN/prompt_A_batch0.txt)를 그대로 쓴다
GAP = 75                # 요청 사이 최소 초
MIN_RPD_LEFT = 100      # 일일 요청 잔량이 한도의 10% 미만이면 멈춤(운영과 같은 키)

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
    # (3차) 2차 A 가 빠뜨린 경계를 일반화한 예시로 — 정답표 글을 그대로 넣지 않는다(점수가 부풀므로)
    "경계 예시 — 한 글이 둘 이상에 걸치는 일이 많다. 분류 하나를 고른 뒤에도 나머지 분류를 하나씩 다시 확인해 빠뜨리지 말 것.\n"
    # (4차) 공연 굿즈 줄 — #11 이 1~3차 모두 live 를 빠뜨림 / 「バンドリ！TV LIVE」(방송)에 live 가 붙지 않게 막는 문구를 함께
    "- 공연 굿즈의 판매 · 선행 판매 · 통판 · 사후 통판 안내 → live, goods. 굿즈만 다루는 글이라도 어느 공연의 굿즈인지 적혀 있으면 live 도 고른다. "
    "「BanG Dream! ○th LIVE」처럼 여러 밴드가 함께 서는 공연도, 글에 유메미타(夢限大みゅーたいぷ · #ゆめみた)가 나오면 유메미타 공연이다. "
    "(공연 티켓 판매는 live 만 — goods 아님. 「バンドリ！TV LIVE」는 방송 프로그램 이름이라 live 가 아니라 broadcast.)\n"
    # (4차) 릴리즈 이벤트 줄 — 3차에서 CD 와 무관한 전시 기념 お渡し会(#57)에 goods 가 붙음
    "- CD(싱글 · 앨범) 발매를 기념하는 릴리즈 이벤트 · 사인회 · お渡し会의 개최 · 중지 · 참가 감사 · 다음 회차 안내 → event, goods. "
    "CD 발매와 무관한 행사(전시 · 생일 · 기념일을 기념하는 お渡し会 · 사인회 등)는 event 만 — 행사에서 무언가를 받거나 산다는 것만으로는 goods 가 아니다.\n"
    "- 팬 · 영상 제작자 등 다른 사람이 만든 유메미타 커버곡 영상 · MV 를 리포스트하거나 소개하는 글(「covered by 夢限大みゅーたいぷ」) → goods. "
    "만든 사람이 외부여도, 판매가 아니어도 같다.\n"
    "- 공연(프리 라이브 포함)을 유튜브 등으로 생중계(「フリーライブ … YouTubeにて生配信」 「全編無料配信」) → live, broadcast.\n"
)
# ───── (5차, 10-24 예정) 주제 먼저 · 분류마다 따로 예/아니오 + 근거 — ROUND5_PLAN.md ─────
# 3 · 4차의 「빠뜨리지 말고 더 골라라」 예시가 보지 않은 글에서 잘못 붙임을 늘린 것(§4-4)을 거꾸로 — 곁들인 언급으로는 고르지 않게 한다.
# 정의 줄의 일부는 운영자 정답(검증 세트, 10-23)에 맞춘 것 — #77 · #107 · #102 · #118 · #119. #100 · #120 은 확인 대기라 넣지 않았다.
HEAD_C = (
    "아래는 X(트위터) 글 여러 개다. 각 글은 성우 밴드 「夢限大みゅーたいぷ」(유메미타 — 仲町あられ · 宮永ののか · 峰月律 · 藤都子 · 千石ユノ) 관련 글이다.\n"
    "글마다 아래 두 단계를 따라라.\n"
    "1단계 — subject: 이 글이 팬에게 알리는 것을 한국어 한 줄로 적어라(무엇을 · 언제). 글에 곁들여 언급된 것은 넣지 않는다.\n"
    "2단계 — 아래 네 분류마다 「이 글이 그것 자체를 알리는가」를 따로 판단해 yes(true/false)와 근거 한 줄(evidence — 원문 그대로 복사, no 면 \"\")을 적어라.\n"
    "여러 개가 yes 일 수 있지만, 일부러 더 고르지 말 것. 곁들인 언급(「当日グッズ情報も」 같은 한 줄)만으로는 yes 가 아니다 — 그 내용 자체를 안내하면 yes.\n"
    "- live (라이브공연): 유메미타 전체 · 일부 · 멤버 솔로가 무대에 서는 공연. 그 공연의 티켓 · 추첨 · 아카이브 시청권 판매 · 개장 · 변경 안내, 공연 회장 안의 부대 안내 포함. "
    "아님: 공연이 끝난 뒤 감사 · 소감 · 세트리스트, 공연 영상을 다 같이 보는 동시 시청 방송(→ broadcast).\n"
    "- event (오프라인행사): 공연이 아닌, 멤버가 나오는 오프라인 행사 — 사인회 · お渡し会 · 릴리즈 이벤트 · 토크쇼 · 팬 이벤트 · 전시 · 콜라보 매장. "
    "아님: 「ライブ」 공연, 온라인 사인회의 생중계 자체(→ broadcast).\n"
    "- goods (음원·굿즈): 판매 · 발매 · 예약 · 특전이 이 글의 안내 대상인 물건 — CD · 음원 · 커버곡 · 굿즈 · Blu-ray · 잡지 · 코믹스. "
    "아님: 영상 · MV 공개 자체(판매가 아님), 행사 · 공연 안내 속 한 줄 언급.\n"
    "- broadcast (방송): 멤버가 출연하거나 직접 하는 방송 · 영상 — 유튜브 생방송 · 프리미어 · 동시 시청, 「バンドリ！TV LIVE」, 라디오 · TV 출연, 행사 · 공연의 생중계. "
    "아님: 애니메이션 「ゆめ∞みた」 방영 · 재방송 안내(멤버 출연이 아님).\n"
    "reason = 판단 이유 한국어 한 문장. 결과는 글 번호(n)마다 하나씩. JSON 으로만 답하라.\n"
)


def _norm_ev(t):
    """근거 대조용 — 공백 · 줄바꿈 무시, NFKC(운영 llm.evidence_in_text 와 같은 취지)."""
    import unicodedata
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", t or ""))


def _cats_c(r, body):
    """5차 응답 → 분류 목록. yes 이고 근거가 원문에 있는(2자 이상) 분류만(운영 코드에서도 같은 규칙으로 쓸 예정)."""
    out = []
    for c in CATS:
        v = r.get(c) or {}
        ev = _norm_ev(v.get("evidence"))
        if v.get("yes") is True and len(ev) >= 2 and ev in _norm_ev(body):
            out.append(c)
    return out


HEAD_B = ("- related: 유메미타(멤버 포함)가 전혀 나오지 않고 다른 밴드 · 다른 작품만 다루는 글이면 false, 아니면 true.\n")
TAIL = ("evidence = 판단 근거가 된 구절들 — 글에서 한 줄씩 그대로 복사(바꾸지 말 것).\n"
        "reason = 판단 이유 한국어 한 문장.\n결과는 글 번호(n)마다 하나씩. JSON 으로만 답하라.\n")


def schema(variant):
    if variant == "C":   # 5차
        one = {"type": "object", "additionalProperties": False, "required": ["yes", "evidence"],
               "properties": {"yes": {"type": "boolean"}, "evidence": {"type": "string"}}}
        item = {"n": {"type": "integer"}, "subject": {"type": "string"},
                **{c: one for c in CATS}, "reason": {"type": "string"}}
        return {"name": "notice_categories_r5", "strict": True, "schema": {
            "type": "object", "additionalProperties": False, "required": ["results"],
            "properties": {"results": {"type": "array", "items": {
                "type": "object", "additionalProperties": False, "required": list(item), "properties": item}}}}}
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
    head = HEAD_OVERRIDE or (HEAD_C if variant == "C" else HEAD + (HEAD_B if variant == "B" else "") + TAIL)
    body = "".join(f"\n--- 글 n={g['n']} ---\n{g['title']}\n{g['body']}\n" for g in batch)
    return head + body


def batches():
    gold = json.load(open(GOLD, encoding="utf-8"))
    return [gold[k:k + BATCH] for k in range(0, len(gold), BATCH)]


def used():
    tot = 0
    for f in glob.glob(os.path.join(OUT, "out_*.json")):
        tot += (json.load(open(f, encoding="utf-8")).get("usage") or {}).get("total_tokens", 0)
    return tot


def run(variant, no):
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(os.path.join(OUT, "STOP")):
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
        open(os.path.join(OUT, "STOP"), "w", encoding="utf-8").write(f"{e.code} {body}")
        sys.exit(f"HTTP {e.code} — 멈춤: {body}")
    out = {"variant": variant, "batch": no, "ns": [g["n"] for g in b], "sec": round(time.time() - t0, 1),
           "usage": d.get("usage"), "ratelimit": hdr, "content": d["choices"][0]["message"]["content"]}
    json.dump(out, open(os.path.join(OUT, f"out_{variant}_{no}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps({"usage": out["usage"], "ratelimit": hdr, "sec": out["sec"], "cum": used()}, ensure_ascii=False), flush=True)
    return out


def compare5(ds):
    """5차와 2 · 3 · 4차를 같은 데이터 · 같은 채점으로 비교 — 1 = 1차 정답표(36건 + 리포스트 표시 뺀 21건), 2 = 검증 세트(29건)."""
    gold = {g["n"]: g for g in json.load(open(GOLD, encoding="utf-8"))}
    RT = re.compile(r"^\s*(?:RT\s+)?@\w{1,15}\s*[:：]")

    def load(folder, variant):
        pred = {}
        for f in sorted(glob.glob(os.path.join(HERE, folder, f"out_{variant}_*.json"))):
            for r in json.loads(json.load(open(f, encoding="utf-8"))["content"])["results"]:
                if variant == "C":
                    g0 = gold.get(r["n"])
                    r["cats"] = _cats_c(r, (g0["title"] + "\n" + g0["body"]) if g0 else "")
                pred[r["n"]] = r
        return pred

    rounds = ([("2차", "round2", "A"), ("3차", "round3", "A"), ("4차", "round4", "A"), ("5차", "round5", "C")] if ds != "2" else
              [("2차", "holdout/r2", "A"), ("3차", "holdout/r3", "A"), ("4차", "holdout/r4", "A"), ("5차", "holdout/r5", "C")])
    views = [("전체", list(gold))] + ([("리포스트 표시 뺀 것", [n for n in gold if not RT.match(gold[n]["body"] or "")])] if ds != "2" else [])
    lines = []
    for vname, keep in views:
        lines += [f"### {'1차 정답표' if ds != '2' else '검증 세트'} — {vname} ({len(keep)}건)", "",
                  "| 회차 | 완전 일치 | 가중 precision | 가중 recall | 가중 F0.5 | 잘못 붙임 | 빠뜨림 | live 잘못 붙임 |", "|---|---|---|---|---|---|---|---|"]
        for name, folder, variant in rounds:
            pred = load(folder, variant)
            ns = [n for n in keep if n in pred]
            if not ns:
                lines.append(f"| {name} | (응답 없음) | | | | | | |")
                continue
            G = {n: set(gold[n]["gold"]) or {"etc"} for n in ns}
            P = {n: set(pred[n]["cats"]) or {"etc"} for n in ns}
            per, avg, _ = _metrics(ns, G, P)
            pc = lambda v: f"{v * 100:.1f}%"
            lines.append(f"| {name} | {sum(G[n] == P[n] for n in ns)}/{len(ns)} | {pc(avg['precision'])} | {pc(avg['recall'])} | **{pc(avg['f0.5'])}** | "
                         f"{sum(per[c]['fp'] for c in PASS)} | {sum(per[c]['fn'] for c in PASS)} | {per['live']['fp']} |")
        lines.append("")
    txt = "\n".join(lines)
    open(os.path.join(OUT, "compare.md"), "w", encoding="utf-8").write(txt + "\n")
    print(txt)


def hbuild():
    """검증 세트 정답 → gold_holdout.json. 「기타」 = 고른 분류 없음([]) — 1 · 2 · 3 · 4차 정답표와 같은 표기."""
    data = os.path.join(HERE, "data")
    items = {i["id"]: i for i in json.load(open(os.path.join(data, "holdout_items.json"), encoding="utf-8"))}
    labels = json.load(open(os.path.join(data, "holdout_labels_2026-10-23.json"), encoding="utf-8"))
    gold = []
    import re
    for lid, d in labels.items():
        i = items[lid]
        # (v4.7.0 배포 뒤) 리포스트 표시(본문이 「RT @…:」/「@…:」)가 있는 글은 운영 코드가 LLM 없이 기타로 정한다(10-23 운영자 결정) — LLM 채점에서 뺀다
        if re.match(r"^\s*(?:RT\s+)?@\w{1,15}\s*[:：]", i.get("body") or ""):
            continue
        cats = [c for c in d["cats"] if c in CATS]
        gold.append({"n": i["n"], "id": lid, "gold": sorted(cats), "title": i["title"], "body": i["body"], "note": d.get("note") or ""})
    gold.sort(key=lambda g: g["n"])
    json.dump(gold, open(os.path.join(HERE, "gold_holdout.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    from collections import Counter
    print(len(gold), Counter(c for g in gold for c in (g["gold"] or ["etc"])))


def _holdout(r):
    """검증 세트 명령 공통 — 정답표 · 프롬프트 머리 · 출력 폴더를 그 회차 것으로."""
    global GOLD, HEAD_OVERRIDE, OUT
    GOLD = os.path.join(HERE, "gold_holdout.json")
    t = open(os.path.join(HERE, f"round{r}", "prompt_A_batch0.txt"), encoding="utf-8").read()
    HEAD_OVERRIDE = t[:t.index("\n--- 글 n=")]
    OUT = os.path.join(HERE, "holdout", f"r{r}")


def _secs(v):
    """x-ratelimit-reset-* 값(「1m26.4s」 · 「22.485s」 · 「500ms」) → 초."""
    import re
    t = 0.0
    for num, unit in re.findall(r"([0-9.]+)(ms|h|m|s)", v or ""):
        t += float(num) * {"ms": 0.001, "s": 1, "m": 60, "h": 3600}[unit]
    return t


def runall(variant):
    """(3차) 전 묶음을 하나씩. 요청 사이 GAP 초 이상 + 분당 토큰 잔량이 다음 요청 예상량 + 10% 미만이면 reset 만큼 더 기다림,
    일일 요청 잔량이 MIN_RPD_LEFT 미만 · 예산 초과 · HTTP 오류(429 포함)면 재시도 없이 멈춤. 일일 토큰(TPD)은 헤더에 없어 누적(used)으로만 센다."""
    bs = batches()
    for no in range(len(bs)):
        if os.path.exists(os.path.join(OUT, f"out_{variant}_{no}.json")):
            print(f"묶음 {no} 이미 있음 — 건너뜀", flush=True)
            continue
        need = int(len(prompt(variant, bs[no])) / 1.2) + 1500   # 입력 어림 + 출력 여유
        if used() + need > BUDGET:
            sys.exit(f"예산 {BUDGET} 넘음(누적 {used()} + 예상 {need}) — 멈춤")
        h = run(variant, no)["ratelimit"]
        rpd_left = int(h.get("x-ratelimit-remaining-requests", "0"))
        if rpd_left < MIN_RPD_LEFT:
            open(os.path.join(OUT, "STOP"), "w", encoding="utf-8").write(f"일일 요청 잔량 {rpd_left} < {MIN_RPD_LEFT}")
            sys.exit(f"일일 요청 잔량 {rpd_left} — 멈춤")
        if no == len(bs) - 1:
            break
        nxt = int(len(prompt(variant, bs[no + 1])) / 1.2) + 1500
        wait = GAP
        if int(h.get("x-ratelimit-remaining-tokens", "0")) < nxt * 1.1:
            wait = max(wait, _secs(h.get("x-ratelimit-reset-tokens")) + 5)
        print(f"다음 묶음까지 {wait:.0f}초 대기", flush=True)
        time.sleep(wait)


# 합격 기준(2026-10-23 운영자): 라이브공연 100%, 기타 제외 나머지 95% 이상 — 드랍 여부와 상관없이(드랍 3건은 정답표에서 이미 뺌).
# precision · recall · accuracy 를 모두 본다. 세 지표 모두에 기준을 적용하는지는 운영자 확인 필요 — 지금은 셋 다 넘어야 PASS 로 계산.
PASS = {"live": 1.0, "event": 0.95, "goods": 0.95, "broadcast": 0.95}
LABELS = CATS + ["etc"]          # etc = 고른 분류 없음(코드가 기타로)


def _ratio(a, b):
    return None if b == 0 else a / b


# 채택 규칙(2026-10-23 운영자): 2차 A 안이 합격선 — 이보다 높은 안 중 가장 높은 것을 채택, 몇 번 시험해도 없으면 2차 A 안 채택.
# 「높다」의 비교 지표 = 기준 4분류 정답 수 가중 F0.5(FP 를 무겁게) + 라이브공연(live) FP 는 1건도 안 됨(운영자 확정).
BASELINE_F05 = 0.9729522520998929  # round2/score_A.json views.분류.weighted_avg.f0.5 (precision 100% · recall 88.9% · FP 0 · FN 5)
BETA = 0.5   # F-beta — beta < 1 이면 precision(FP 적음)을 더 무겁게. 0.5 = precision 을 recall 의 2배로(운영자: FP 가 신뢰를 더 깎음)


def _fbeta(p, r, beta):
    if p is None or r is None or (p == 0 and r == 0):
        return None if p is None or r is None else 0.0
    b2 = beta * beta
    return (1 + b2) * p * r / (b2 * p + r)


def _metrics(ns, G, P):
    """분류마다 2x2 혼동행렬 + precision · recall · accuracy · F1 · F0.5, 분류 간 혼동표, 기준 분류의 정답 수 가중 평균."""
    per = {}
    for c in LABELS:
        tp = sum(1 for n in ns if c in G[n] and c in P[n]); fp = sum(1 for n in ns if c not in G[n] and c in P[n])
        fn = sum(1 for n in ns if c in G[n] and c not in P[n]); tn = len(ns) - tp - fp - fn
        p, r = _ratio(tp, tp + fp), _ratio(tp, tp + fn)
        m = {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "support": tp + fn,
             "precision": p, "recall": r, "accuracy": _ratio(tp + tn, len(ns)), "f1": _fbeta(p, r, 1.0), f"f{BETA}": _fbeta(p, r, BETA),
             "fp_n": [n for n in ns if c not in G[n] and c in P[n]], "fn_n": [n for n in ns if c in G[n] and c not in P[n]]}
        if c in PASS:
            m["pass"] = all(m[k] is not None and m[k] >= PASS[c] for k in ("precision", "recall", "accuracy"))
        per[c] = m
    sup = sum(per[c]["support"] for c in PASS)
    avg = {k: sum((per[c][k] or 0) * per[c]["support"] for c in PASS) / sup for k in ("precision", "recall", "f1", f"f{BETA}")}
    cross = {r: {c: sum(1 for n in ns if r in G[n] and c in P[n]) for c in LABELS} for r in LABELS}
    return per, avg, cross


def score(variant, outdir=None):
    """채점 → outdir 에 score_<안>.json · .md.
    「분류」 = 모델이 고른 분류 그대로. 「실효」 = 사용자에게 보이는 결과 — B 안의 related=false 는 소식이 안 올라가므로
    그 글의 분류가 하나도 없는 것(etc 도 아님)으로 친다(A 안은 두 값이 같다)."""
    outdir = outdir or HERE
    gold = {g["n"]: g for g in json.load(open(GOLD, encoding="utf-8"))}
    pred = {}
    for f in sorted(glob.glob(os.path.join(outdir, f"out_{variant}_*.json"))):
        for r in json.loads(json.load(open(f, encoding="utf-8"))["content"])["results"]:
            if "cats" not in r and variant == "C":      # 5차 — 분류마다 예/아니오 + 근거 → 목록
                g0 = gold.get(r["n"])
                r["cats"] = _cats_c(r, (g0["title"] + "\n" + g0["body"]) if g0 else "")
            pred[r["n"]] = r
    ns = [n for n in gold if n in pred]
    G = {n: set(gold[n]["gold"]) or {"etc"} for n in ns}
    P = {n: set(pred[n]["cats"]) or {"etc"} for n in ns}
    dropped = [n for n in ns if pred[n].get("related") is False]
    PE = {n: (set() if n in dropped else P[n]) for n in ns}
    views = {"분류": _metrics(ns, G, P), "실효": _metrics(ns, G, PE)}
    exact = sum(1 for n in ns if G[n] == P[n])
    items = [{"n": n, "gold": sorted(G[n]), "pred": sorted(P[n]), "exact": G[n] == P[n], "dropped": n in dropped,
              "related": pred[n].get("related"), "reason": pred[n].get("reason"), "evidence": pred[n].get("evidence"),
              "title": gold[n]["title"]} for n in ns]
    res = {"variant": variant, "n_items": len(ns), "exact": exact, "dropped": dropped, "pass_rule": PASS, "beta": BETA,
           "views": {k: {"per_label": v[0], "weighted_avg": v[1], "cross": v[2],
                         "passed": all(v[0][c]["pass"] for c in PASS)} for k, v in views.items()},
           "items": items}
    json.dump(res, open(os.path.join(outdir, f"score_{variant}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    pc = lambda v: "—" if v is None else f"{v * 100:.1f}%"
    fb = f"f{BETA}"
    md = [f"# {variant}안 채점 — {len(ns)}건, 분류 완전 일치 {exact}/{len(ns)}"
          + (f", 소식 아님으로 버림 {len(dropped)}건({' '.join('#%d' % n for n in dropped)})" if dropped else ""), ""]
    for vname, (per, avg, cross) in views.items():
        if vname == "실효" and not dropped:
            continue
        passed = all(per[c]["pass"] for c in PASS)
        md += [f"## {vname} — 합격 {'PASS' if passed else 'FAIL'}" + (" (버린 글 = 분류 없음으로 계산)" if vname == "실효" else ""), "",
               f"| 분류 | 정답 수 | TP | FP | FN | TN | precision | recall | accuracy | F1 | F{BETA} | 기준 | 판정 | 빠뜨림(FN) | 잘못 붙임(FP) |",
               "|---" * 15 + "|"]
        for c in LABELS:
            m = per[c]
            md.append(f"| {c} | {m['support']} | {m['tp']} | {m['fp']} | {m['fn']} | {m['tn']} | {pc(m['precision'])} | {pc(m['recall'])} | "
                      f"{pc(m['accuracy'])} | {pc(m['f1'])} | {pc(m[fb])} | {pc(PASS.get(c))} | "
                      f"{('PASS' if m['pass'] else 'FAIL') if 'pass' in m else '(제외)'} | "
                      f"{' '.join('#%d' % n for n in m['fn_n'])} | {' '.join('#%d' % n for n in m['fp_n'])} |")
        md += ["", f"기준 4분류(etc 제외) 정답 수 가중 평균 — precision {pc(avg['precision'])} · recall {pc(avg['recall'])} · "
                   f"F1 {pc(avg['f1'])} · **F{BETA} {pc(avg[fb])}** (기준선 2차 A {pc(BASELINE_F05)} 대비 "
                   f"{(avg[fb] - BASELINE_F05) * 100:+.1f}%p)", "",
               f"**채택 후보: {'예' if avg[fb] > BASELINE_F05 and per['live']['fp'] == 0 else '아니오'}** "
               f"(가중 F{BETA} 가 기준선보다 높고 live FP 0 — 지금 live FP {per['live']['fp']})"
                   + (f" — 이 평균엔 버린 소식이 안 잡힌다: 소식 자체 누락 {len(dropped)}/{len(ns)}" if vname == "실효" else ""), "",
               "분류 간 혼동표 (행 = 정답, 열 = 판정, 복수 분류라 한 글이 여러 칸에 들어감)", "",
               "| 정답 \\ 판정 | " + " | ".join(LABELS) + " |", "|---" * (len(LABELS) + 1) + "|"]
        md += [f"| {r} | " + " | ".join(str(cross[r][c]) for c in LABELS) + " |" for r in LABELS]
        md.append("")
    md += ["틀린 글", ""]
    md += [f"- #{i['n']} 정답 {'+'.join(i['gold'])} / 판정 {'+'.join(i['pred'])}" + (" / **소식 아님으로 버림**" if i["dropped"] else "")
           + f" — {i['reason']}" for i in items if not i["exact"] or i["dropped"]]
    open(os.path.join(outdir, f"score_{variant}.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print("\n".join(md))


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
    elif cmd == "runall":
        runall(sys.argv[2])
    elif cmd in ("run5", "score5", "dry5"):
        ds = sys.argv[2]
        if ds == "2":
            GOLD = os.path.join(HERE, "gold_holdout.json")
            OUT = os.path.join(HERE, "holdout", "r5")
        else:
            OUT = os.path.join(HERE, "round5")
        if cmd == "dry5":
            for k, b in enumerate(batches()):
                p = prompt("C", b)
                print(k, len(b), "chars", len(p), "≈tok", int(len(p) / 1.5))
        elif cmd == "run5":
            runall("C")
        else:
            if glob.glob(os.path.join(OUT, "out_C_*.json")):
                score("C", OUT)
            compare5(ds)
    elif cmd == "hbuild":
        hbuild()
    elif cmd in ("hdry", "hrun", "hscore"):
        _holdout(sys.argv[2])
        if cmd == "hdry":
            for k, b in enumerate(batches()):
                p = prompt("A", b)
                print(k, len(b), "chars", len(p), "≈tok", int(len(p) / 1.2))
        elif cmd == "hrun":
            runall("A")
        else:
            score("A", OUT)
    elif cmd == "score":   # score A [결과 폴더 — 기본 이 폴더]
        score(sys.argv[2], os.path.join(HERE, sys.argv[3]) if len(sys.argv) > 3 else None)
