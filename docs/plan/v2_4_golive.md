# X 릴레이 실배포 전환 런북 (v2.4)

다른 세션이 "이제 실제로 반영되게 켜자" 를 할 때 이 문서대로.

![v2.4 전체 흐름](v2_4_flow.png)

*(생성기 `docs/plan/gen_v2_4.py` — `python docs/plan/gen_v2_4.py`)*

---

## 구성요소 (그림의 각 박스)

### 외부 · 운영자 폰
- **Android · Automate** — 운영자가 `@BDP_yumemita` 를 팔로우. 삼성 브라우저 웹푸시 알림이 뜨면
  "HTTP Request" 블록이 `POST /ingest` (`X-Ingest-Secret` 헤더). Content body 식:
  ```
  urlEncode({"text": coalesce(nx["android.bigText"], nmsg, nticker, ntitle, "")})
  ```
  - Automate 문자열 연결은 `++` (‘+’는 산술 → `NaN`). `urlEncode(딕셔너리)` 가 `key=value&key=value`
    로 만들어 줌 → `text=` 접두어·URL 인코딩 자동.
  - 이 기기(SM-S911N)에서 실측: 알림 내용은 **`nmsg`(= `android.text` extra)** 에 온다.
    `nx["android.bigText"]` 는 항상 비어있음(보험으로 첫 순위 유지). `nmsg` 가 232자 여러 줄
    전문도 그대로 담았다(잘림 없음). `nticker` 는 안 씀. `ntitle` = 다운로드면 파일명, X 면 계정명.
    `Notification Posted` 트리거 출력: message→`nmsg`, title→`ntitle` (둘 다 유효 변수).
  - `@BDP_yumemita` 알림엔 **본인 글 + 리트윗**(BanG Dream 홍보 계정)이 섞여 온다(본문이 `@원계정: …`).
  - 내용 없는 알림(X 요약/미디어/갱신)은 coalesce 가 `""` → `text=` 빈값 → 백엔드가 `looks_relayable`
    False 로 무시. 무해.
  - 테스트 기간엔 폰 필터 생략, **실배포 시 본문 마커 `配信スケジュール`/`出演情報` 로 필터 복원**
    (발신자 한정은 리트윗을 못 거름).
- **운영자 Telegram DM** — ECHO 원문 + `tail_ok`(말미 고정문구 `※時刻は予告なく変更…` 도착 여부) /
  반영 결과 / 대기열 N건을 회신.

### 백엔드 · Cloud Run + GitHub
- **mewtype-telegram · POST /ingest** (공개, `--allow-unauthenticated`, `X-Ingest-Secret` 검증)
  - **테스트** (`INGEST_ECHO=1` 또는 `INGEST_DRY_RUN=1`): 파싱·저장 안 함. 받은 텍스트 DM 회신 +
    `ingest ECHO: len=.. clen=.. tail_ok=..` 로그. 스케줄/출연 트윗(`xrelay.looks_relayable` —
    본문에 `配信スケジュール` 또는 `出演情報` 계열 마커)만 `ingest_queue.json` 에 원문 적재.
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

## 0. 지금 상태 (2026-09-03 저녁 기준)

- `mewtype-telegram` = `-00012` · **테스트 모드**. env `INGEST_ECHO=1`, `INGEST_DRY_RUN=1`.
  `main`(PR #8 `parse_appearance` 포함)으로 재배포됨.
  - `/ingest` 는 파싱·저장을 안 한다. 받은 텍스트를 DM 으로 돌려주고(`말미문구 ✅/❌`),
    `ingest ECHO: len=.. clen=.. tail_ok=..` 로그를 남기고, 스케줄/출연 트윗이면
    (`xrelay.looks_relayable`) `data` 브랜치 `ingest_queue.json` 에 원문을 적재한다.
- `mewtype-backend` = `-00013` (v2.3+v2.4 `reconcile`). 정기 `/tick` 은 이미 v2.4 로직.
- 프론트(Vercel) = `main` 자동배포됨. `.card--scheduled` / `.card--collab` 코드 있음.
  단 `schedule.json` 에 그런 행이 없어 화면 변화는 아직 없음.
- **아직 프로덕션 `schedule.json` 엔 X 릴레이 유래 행이 하나도 없다. 큐도 비어있다.**

### 폰(Automate) 상태 — 2026-09-03 밤 디버깅 완료

- 테스트 기간 동안 **`Expression true?` 필터를 생략**하고 삼성 브라우저 알림을 전부
  `/ingest` 로 보낸다 (다운로드·리트윗 등 잡 알림도 옴 — ECHO 라 무해, `looks_relayable` 가 큐를 막음).
- **HTTP Request 블록 Content body 식** (운영용, 확정):
  ```
  urlEncode({"text": coalesce(nx["android.bigText"], nmsg, nticker, ntitle, "")})
  ```
  거쳐온 함정:
  - `NaN` 만 보내던 버그: Automate 문자열 연결은 `+` 가 아니라 **`++`** (`+` 는 산술).
  - `urlEncode(딕셔너리)` → `key=value&key=value` (`text=` 접두어·URL 인코딩 자동).
- **필드 실측** (SM-S911N, ECHO 진단 body 로 확인):
  - 알림 내용은 `nmsg` (= `android.text` extra) 에 온다. **`nx["android.bigText"]` 는 항상 비어있음.**
  - `nmsg` 가 232자·12줄 트윗 전문을 그대로 담았다 → 이 길이까진 잘림 없음.
  - `nticker` 안 씀. `ntitle` = 다운로드면 파일명 / X 면 계정명. `ntitle` 도 유효 변수.
  - 내용 없는 알림(X 요약/미디어/갱신 이벤트): 전 필드 빈값 → `coalesce` → `""` → `text=` 빈값 전송
    → 백엔드 `looks_relayable` False 로 무시. (로그: `ingest ECHO: len=0 clen=5`)

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

- `tail_ok=True` → 말미 고정문구(`※時刻は予告なく変更…`)까지 도착 = **안 잘림**. 전환 진행.
- `tail_ok=False` → 잘림. 전환 전에 `xrelay.merge_scheduled` 에 부분 upsert 가드
  추가 (그 함수 상단 `# ponytail:` 주석 위치). 안 그러면 잘린 트윗이 그 날짜의
  온전한 기존 행을 덮어써서 엔트리가 사라진다.
- 트윗이 안 와서 판정 못 해도 전환은 가능하다 — 큐/merge 가 replace-by-date 라
  다음 온전한 트윗이 오면 자동 교체되고, 최악의 경우 하루치가 부분 노출될 뿐이다.

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

## 6. 관련 파일

| | |
|---|---|
| 파서·머지 | `src/backend/xrelay.py` (`parse_bdp_schedule`, `merge_scheduled`) |
| `/ingest`·큐 | `src/backend/telegram_app.py` (`_ingest_queue_push/_drain`, `_merge_rows_into_schedule`) |
| 보존·정리 | `src/collector/reconcile.py` (`build_schedule` scheduled 블록) |
| 프론트 | `src/frontend/js/render.js` (`createCard` scheduled/collab, `renderBoard` 팬아웃), `css/card.css` |
| 계약 | `docs/IMPLEMENTATION.md` §1-1 (scheduled 행 스키마, `host` 필드) |
| 설계 | `docs/plan/v2_3_x_relay.md` (X 릴레이), `docs/plan/v2_4_collab.md` (합동방송) |
| env | `deploy/deploy_telegram.sh` (`INGEST_ECHO` / `INGEST_DRY_RUN` = `${...:-0}`) |
