# X 릴레이 실배포 전환 런북 (v2.4)

다른 세션이 "이제 실제로 반영되게 켜자" 를 할 때 이 문서대로.

![v2.4 전체 흐름](v2_4_flow.png)

*(생성기 `docs/plan/gen_v2_4.py` — `python docs/plan/gen_v2_4.py`)*

---

## 구성요소 (그림의 각 박스)

### 외부 · 운영자 폰
- **Android · Automate** — 운영자가 `@BDP_yumemita` 를 팔로우. 삼성 브라우저 웹푸시 알림이 뜨면
  "HTTP Request" 블록이 `POST /ingest` (`X-Ingest-Secret` 헤더). Content body 식
  (**커밋 `1c21d9a` 기준 — 이걸 그대로 쓴다**):
  ```
  urlEncode({"text": coalesce(nx["android.bigText"], nx["android.text"], nmsg, nticker, "")})
  ```
  - **`coalesce` 를 쓴다, `||` 아님.** 이 폰 Automate 빌드에서 `||` 는 문자열 피연산자에
    **매번 빈값**을 뱉는다. `coalesce` 는 `nx["android.bigText"]` → `nx["android.text"]` → …
    순서로 물어 트윗 본문(여러 줄 전문 포함)을 그대로 가져온다. (2026-09-04 부계정 트윗으로 확정.)
  - **⚠️ 이 빌드의 `urlEncode({"text": expr})` 버그**: 딕셔너리를 `key=value` 로 만들 때 `expr`
    의 **값이 `text` 의 값이 아니라 키 자리로 샌다**. 즉 실제로 전송되는 body 는
    `<URL인코딩된 트윗본문>=` (값은 빈 문자열, `text` 키는 없음).
  - **백엔드 우회** (`telegram_app.py` `_ingest`, `# ponytail:` 표시): `text` 값이 비었고
    (`text`/`title` 외) 정체불명 폼 키가 딱 하나, 그 값도 비어 있으면 → **그 키 이름을 원문으로
    복구**한다. Flask 가 폼 키를 URL 디코드하므로 개행·일본어·`#`·`=`·`&` 다 관통. `xrelay.parse`
    는 평소대로 동작. 폰에서 `"text=" ++ urlEncode(...)` 로 제대로 보낼 수 있게 되면 이 블록 삭제.
  - `++` 는 이 빌드에서도 정상(문자열 연결). `+` 는 산술 → `NaN`. `arrayJoin`/`arrayLength` 등은
    이 빌드에 없는 함수 (`join(c,delim)` + `#` 연산자가 정식이나 이 경로에선 안 씀).
  - 실측: 트윗 본문은 `nx["android.bigText"]` / `nx["android.text"]` 에 온다. 232자 여러 줄 전문도
    잘림 없이 담긴다. `nticker` 안 씀. `ntitle` = 다운로드면 파일명, X 면 계정명.
    X **원글**(팔로우 계정 새 글) 알림은 `InboxStyle` 이고 트리거 발화 시점엔 `textLines` 가
    빈 배열 → 본문 못 잡는 경우가 있다. **리트윗·인용 알림**은 본문이 extra 에 실려 관통.
  - `@BDP_yumemita` 알림엔 **본인 글 + 리트윗**(BanG Dream 홍보 계정)이 섞여 온다(본문이 `@원계정: …`).
  - 내용 없는 알림(X 요약/미디어/갱신)은 body 가 빈 폼 키조차 안 만들거나 `text` 빈값 → 백엔드
    `looks_relayable` False 로 무시. 무해.
  - 테스트 기간엔 폰 필터 생략, **실배포 시 본문 마커 `配信スケジュール`/`出演情報` 로 필터 복원**
    (발신자 한정은 리트윗을 못 거름).
- **운영자 Telegram DM** — ECHO 원문 + `tail_ok`(말미 고정문구 `※時刻は予告なく変更…` 도착 여부) /
  반영 결과 / 대기열 N건을 회신.

### 백엔드 · Cloud Run + GitHub
- **mewtype-telegram · POST /ingest** (공개, `--allow-unauthenticated`, `X-Ingest-Secret` 검증)
  - **테스트** (`INGEST_ECHO=1` 또는 `INGEST_DRY_RUN=1`): 파싱·저장 안 함. 받은 텍스트 DM 회신 +
    `ingest ECHO: len=.. clen=.. tail_ok=..` 로그. 스케줄/출연 트윗(`xrelay.looks_relayable` —
    본문에 `配信スケジュール` 또는 `出演情報` 마커)만 `ingest_queue.json` 에 원문 적재.
  - **실배포** (`INGEST_ECHO=0` · `INGEST_DRY_RUN=0`): `control.json` `paused` 확인 →
    `_ingest_queue_drain` 이 큐 원문을 `received_at` 순서로 `xrelay.parse`(일일 스케줄 →
    없으면 `parse_appearance`) → `merge_scheduled` → `schedule.json` 커밋, 큐 비움. 이번 요청 본문도 파싱·머지.
- **GitHub `data` 브랜치** — `schedule.json`(`status:"scheduled"` 행 = `video_id` 없음,
  `host:"group"` = 5인 공동명의 채널 방송) · `ingest_queue.json`(테스트 기간 버퍼).
- **mewtype-backend · 정기 /tick** (비공개, OIDC) — `reconcile.build_schedule`:
  scheduled 행 보존, 같은 채널 실물 `upcoming`/`live` 가 ±4h 안이면 supersede,
  `expires_at`(start + 공개 3h / 회원전용 5h) 도달 시 제거, `scheduled_start` 지나면 `assumed_live`.
  **`host:"group"` 행은 멤버 개인 채널 실물로 supersede 하지 않는다**(그룹 채널은 추적 5채널이
  아님 → TTL 로만 소멸).

### 프론트엔드
- **프론트 (Vercel)** — `schedule.json` 75s 폴링. `.card--scheduled`(예고, 점선·감광),
  `.card--collab`(합동 — `xrelay` 가 `kind=="collab"` 행에 `host="group"` + 영상 URL 을 채우고,
  `render.js` 가 참여 멤버 전원 `channel_key ∪ collab_with` 레인에 같은 카드로 팬아웃).

### 화살표
| | |
|---|---|
| 알림 본문 | `text=` form 필드 (Automate → `/ingest`) |
| ECHO / 결과 DM | Telegram `sendMessage` (mewtype-telegram → 운영자) |
| 커밋 / 큐 | GitHub Contents API (schedule.json 커밋 / ingest_queue.json 적재·drain) |
| reconcile | 정기 `/tick` 이 `data` 브랜치 읽기·쓰기 |
| raw fetch | `raw.githubusercontent.com/.../data/schedule.json` (프론트 폴링) |

---

## 0. 지금 상태 (2026-09-04 기준)

- `mewtype-telegram` · **테스트 모드**. env `INGEST_ECHO=1`, `INGEST_DRY_RUN=1`.
  **폼 키→원문 복구 우회 포함해 재배포됨** (2026-09-04). 부계정 트윗으로 ECHO DM `text` 영역에
  본문 관통 확인.
  - `/ingest` 는 파싱·저장을 안 한다. 받은 텍스트를 DM 으로 돌려주고(`말미문구 ✅/❌`),
    `ingest ECHO: len=.. clen=.. tail_ok=..` 로그를 남기고, 스케줄/출연 트윗이면
    (`xrelay.looks_relayable`) `data` 브랜치 `ingest_queue.json` 에 원문을 적재한다.
- `mewtype-backend` = `-00013` (v2.3+v2.4 `reconcile`). 정기 `/tick` 은 이미 v2.4 로직.
- 프론트(Vercel) = `main` 자동배포됨. `.card--scheduled` / `.card--collab` 코드 있음.
  단 `schedule.json` 에 그런 행이 없어 화면 변화는 아직 없음.
- **아직 프로덕션 `schedule.json` 엔 X 릴레이 유래 행이 하나도 없다. 큐도 비어있다.**

### 폰(Automate) 상태 — 2026-09-04 body 식 확정 (커밋 `1c21d9a` 기준)

- 테스트 기간 동안 **`Expression true?` 필터를 생략**하고 삼성 브라우저 알림을 전부
  `/ingest` 로 보낸다 (다운로드·리트윗 등 잡 알림도 옴 — ECHO 라 무해, `looks_relayable` 가 큐를 막음).
- **HTTP Request 블록 Content body 식** (운영용, 확정 — 커밋 `1c21d9a` 그대로):
  ```
  urlEncode({"text": coalesce(nx["android.bigText"], nx["android.text"], nmsg, nticker, "")})
  ```
  거쳐온 함정 (전부 이 폰 Automate 빌드 특유):
  - `NaN` 만 보내던 버그: 문자열 연결은 `+` 가 아니라 **`++`** (`+` 는 산술).
  - **`||` 는 매번 빈값**을 뱉었다 → `coalesce` 로 전환. `coalesce` 는 정상 동작
    (2026-09-04 부계정 트윗으로 확인 — text 영역에 본문 정확히 관통).
  - **`urlEncode({"text": expr})` 의 값이 키 자리로 샌다**: 실제 전송 body 는
    `<URL인코딩된 본문>=` (`text` 키 없음, 값 빔). → **백엔드가 폼 키에서 원문 복구**
    (`telegram_app.py` `_ingest`, `# ponytail:`). `text` 값이 비고 정체불명 키 1개+그 값도
    비면 키 이름을 `raw` 로. self-test `[Test 5] ✓ 폼 키로 온 원문 복구`.
  - `arrayJoin`/`arrayLength` = 없는 함수. `join(c,delim)`+`#` 이 정식이나 이 경로에선 불필요.
- **필드 실측** (ECHO 진단으로 확인):
  - 트윗 본문은 `nx["android.bigText"]` / `nx["android.text"]` 에 온다. 232자·12줄 전문도 잘림 없음.
  - `nticker` 안 씀. `ntitle` = 다운로드면 파일명 / X 면 계정명.
  - **X 원글**(팔로우 계정 새 글) 알림 = `android.template` `InboxStyle`, 트리거 시점 `textLines`
    빈 배열 → 본문 못 잡는 케이스 있음. **리트윗·인용**은 extra 에 실려 관통.
  - 내용 없는 알림(X 요약/미디어/갱신): 폼 키조차 안 생기거나 `text` 빈값 → 백엔드
    `looks_relayable` False 로 무시. (로그: `ingest ECHO: len=0`)

## 1. 전환 전 확인 — 웹푸시 잘림 (#1)

폰(Automate)이 삼성 브라우저 웹푸시 알림을 relay 할 때 본문이 "Show more" 로
잘리는지. **2026-09-03 밤: `@bang_dream_info` 232자·12줄 / `@bang_dream_on` 182자
트윗이 전문 그대로 관통 확인** (`ingest ECHO: len=232 clen=1100` 등, head/tail 에 끝까지).
→ `nmsg`(android.text) 가 펼친 전문을 담고 있고 이 길이까진 잘림 없음. 다만 일일
`配信スケジュール` 는 더 길 수 있으니(400~600자) 실물 스케줄 트윗으로 한 번 더 확인 권장.

- 아직 못 본 것: `@BDP_yumemita` 의 실제 「配信スケジュール」 / `出演情報` 트윗.
  오면 ECHO DM `말미문구 ✅/❌` + 아래 로그의 `tail_ok` 로 판정.
- 테스트 기간엔 폰 `Expression true?` 필터를 **생략**하고 삼성 브라우저 알림을 전부
  `/ingest` 로 보내는 중. `@BDP_yumemita` 팔로우 알림에는 **본인 글뿐 아니라 리트윗**
  (`@bang_dream_info`, `@bang_dream_on` 등 BanG Dream 홍보 계정)도 섞여 온다 —
  알림 본문이 `@원계정: …` 로 시작. 전부 `/ingest` ECHO 로 왕복하지만
  `looks_relayable`(본문에 `配信スケジュール`/`出演情報` 마커) 이 아니면 큐·파싱 안 탐. 확인됨:
  182자·232자 리트윗 2건 → `form_keys=['text']`, 전문 관통, `ingest_queue.json` 그대로 `{"pending":[]}`.
- **실배포 시 필터 복원**: 발신자 한정으로는 리트윗을 못 거른다 → 폰 필터도 백엔드와 같이
  **본문 마커 `配信スケジュール` / `出演情報`** 로 걸 것. 안 그러면 홍보 리트윗이 계속 `/ingest` 로 온다.

```bash
gcloud logging read \
  'resource.labels.service_name="mewtype-telegram" AND textPayload:"ingest ECHO"' \
  --limit 5 --format='value(timestamp,textPayload)'
```

### 실물 키워드 알림이 오면 — 판정

DM 텍스트 원문을 확보하고 (또는 로그 head/tail), 잘림 여부를 이렇게 본다:

- **日次 `配信スケジュール`**: 마지막 줄이 `※時刻は予告なく変更…` → `tail_ok=True` 면 안 잘림.
- **`出演情報`**: `※時刻は…` 로 안 끝나므로 `tail_ok` 는 항상 False(오탐). 대신
  `xrelay.parse_appearance(원문, now)` 를 돌려 `url`(`youtube.com/live/<11자>`)이 잡히면 온전,
  `None`/`[]` 면 잘림 의심. 일반적으론 `xrelay.parse(원문, now)` 로 (a) 잘림 여부 (b) 파싱 결과
  (채널·시각·`host`)를 함께 확인.
- ECHO 모드여도 이 트윗은 `looks_relayable` 통과라 `ingest_queue.json` 에 원문이 **자동 적재**된다.

### CASE A — 본문 전부 살아서 옴

1. `xrelay.parse` 로 기대한 행이 나오는지 확인.
2. **실배포 전환** (§2).
3. 전환 후 첫 `/ingest` 가 큐 drain → 그동안 쌓인 트윗 반영. 즉시 반영하려면 원문을 curl 로 한 번 더
   (§3 하단).
4. **검증** (§4): `schedule.json` 에 `scheduled`/`collab` 행 + 프론트 카드.
5. **폰 필터 복원**: `Expression true?` 를 본문에 `配信スケジュール` OR `出演情報` 포함으로 →
   리트윗·잡음 차단.

### CASE B — 본문이 잘려서 옴

1. 정말 잘림인지 확인(짧지만 완결된 트윗과 구분 — 문장/엔트리 중간에서 끊겼나).
2. **전문 회수** (택1):
   - 폰에서 그 알림을 펼쳐(tap) Automate 가 `nx["android.bigText"]` 채운 채 재발화하는지
     (bigText 는 펼친 뒤에만 생기기도 함).
   - X 에서 트윗 열어 본문 복사 → curl 로 `/ingest`. 큐에 들어가며, 나중 온전본이 날짜 기준
     `merge_scheduled` replace-by-date 로 잘린본을 교체.
   - `cdn.syndication.twimg.com/tweet-result?id=<트윗ID>` (ID 있으면).
3. **`xrelay.merge_scheduled` 에 잘림 가드 추가** (`# ponytail:` 주석 위치) — "그 날짜 새 엔트리 수
   < 기존 수 → replace 대신 upsert". 잘린 트윗이 온전본이 만든 행을 지우지 않게. **코드 변경 → PR.**
4. 가드 넣은 뒤 실배포 전환(§2~§4). 이후 잘린 트윗이 와도 데이터 안 깨지고 다음 온전본/수동 curl 이
   마저 채운다.
5. 폰 필터 복원.

### 트윗이 안 와서 판정 못 해도

전환은 가능하다 — 큐/merge 가 replace-by-date 라 다음 온전한 트윗이 오면 자동 교체되고, 최악의
경우 하루치가 부분 노출될 뿐이다. (안전을 원하면 CASE B 3의 가드를 먼저 넣고 전환.)

## 2. 전환

```bash
gcloud run services update mewtype-telegram --region asia-northeast1 \
  --update-env-vars INGEST_ECHO=0,INGEST_DRY_RUN=0
```

env 만 바꾸므로 재빌드 없음(새 리비전 1개). 코드 배포가 필요하면
`INGEST_ECHO=0 INGEST_DRY_RUN=0 bash deploy/deploy_telegram.sh` (env.sh 에
두 값이 없으므로 export 로 넘겨야 함 — `deploy_telegram.sh` 는 `${...:-0}`).

## 3. 전환 직후 동작

전환 후 **첫 `/ingest`** (폰 트윗이든, 아래 수동 트리거든) 에서:

1. `control.json` `paused` 확인 (paused 면 스킵).
2. `_ingest_queue_drain` — `ingest_queue.json` 의 원문을 `received_at` 순서대로
   `xrelay.parse_bdp_schedule` → `merge_scheduled`. 큐를 비운다.
3. 이번 요청 본문도 파싱·머지.
4. 요약 DM 에 `📥 대기열 N건(M행) 반영` 표기.

→ 테스트 기간에 폰에서 온 트윗이 유실 없이 반영된다.
빈 큐면 drain 은 즉시 no-op (읽기 1회).

수동으로 큐만 먼저 흘리고 싶으면 아무 스케줄 트윗이나 재전송:

```bash
SECRET=$(gcloud secrets versions access latest --secret=INGEST_SECRET)
curl -sS -X POST https://mewtype-telegram-376735243718.asia-northeast1.run.app/ingest \
  -H "X-Ingest-Secret: $SECRET" --data-urlencode "text@<트윗원문파일>"
```

## 4. 검증

```bash
# schedule.json 에 scheduled / collab 행이 들어갔나
curl -s "https://raw.githubusercontent.com/sbb2002/mewtype-scheduler/data/schedule.json" \
  | python -c "import sys,json; b=json.load(sys.stdin)['broadcasts']; \
      print([(x['channel_key'], x.get('status'), x.get('kind'), x.get('host')) \
             for x in b if x.get('status')=='scheduled'])"
```

- 프론트: 예고 카드(`.card--scheduled`) / 합동 카드(`.card--collab`, 참여 멤버
  전원 레인)가 뜨는지. raw CDN 캐시로 최대 ~5분 지연.
- 정기 `/tick` 후 `reconcile` 이 실물 `upcoming` supersede / `expires_at` 정리
  하는지 (`host="group"` 행은 멤버 실물로 supersede 안 됨 — TTL 로만).

## 5. 롤백

```bash
gcloud run services update mewtype-telegram --region asia-northeast1 \
  --update-env-vars INGEST_ECHO=1,INGEST_DRY_RUN=1
```

이미 `schedule.json` 에 쓰인 행은 그대로 남는다. 지우려면:
- 잠깐 기다리면 `expires_at`(start+3~5h) 지나며 다음 `/tick` 이 제거, 또는
- `data` 브랜치 `schedule.json` 에서 해당 `broadcasts[]` 항목 직접 삭제 커밋.

## 6. 열린 것 / 후속

- **`生配信中` (라이브 시작 알림) 미처리.** `@BDP_yumemita` 는 `配信スケジュール`·`出演情報` 외에
  `＼生配信中📢／ … 同時視聴配信 #N … youtube.com/live/<id>` 형태 라이브 시작 트윗도 낸다
  (arale×nonoka 그룹 채널 애니 동시시청, 정기 시리즈). 그룹 채널 라이브는 추적 5채널 RSS/API 로
  안 잡히니 이 트윗이 유일한 라이브 시작 신호. **결정 대기**: `parse_live_now` 추가해 `host="group"`
  collab 행 `assumed_live=true` 로 승격(같은 `url` 의 기존 scheduled 행이 있으면 그걸 승격, 중복 방지)
  → `looks_relayable` 에 `生配信中` 마커 추가 → PR. 안 하면 그룹 합동은 예고 단계까지만 뜨고 조용히 만료.
- **CASE B 잘림 가드** (`merge_scheduled` `# ponytail:`): 미구현. 실물 스케줄 트윗이 잘려 오면 그때.
- **파서 B (멤버 개인 트윗)**: v2.3 §3-2, 후속.

## 7. 관련 파일

| | |
|---|---|
| 파서·머지 | `src/backend/xrelay.py` (`parse` / `parse_bdp_schedule` / `parse_appearance`, `merge_scheduled`, `looks_relayable`) |
| `/ingest`·큐 | `src/backend/telegram_app.py` (`_ingest` — 폼 키→원문 복구 `# ponytail:`, `_ingest_queue_push/_drain`, `_merge_rows_into_schedule`) |
| 보존·정리 | `src/collector/reconcile.py` (`build_schedule` scheduled 블록) |
| 프론트 | `src/frontend/js/render.js` (`createCard` scheduled/collab, `renderBoard` 팬아웃), `css/card.css` |
| 계약 | `docs/IMPLEMENTATION.md` §1-1 (scheduled 행 스키마, `host` 필드) |
| 설계 | `docs/plan/v2_3_x_relay.md` (X 릴레이), `docs/plan/v2_4_collab.md` (합동방송) |
| env | `deploy/deploy_telegram.sh` (`INGEST_ECHO` / `INGEST_DRY_RUN` = `${...:-0}`) |
