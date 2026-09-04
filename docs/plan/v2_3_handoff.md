# v2.3 X 릴레이 — 핸드오프

작성 2026-09-03. 다른 세션이 이어받을 때 여기부터.

- **브랜치**: `feat/x-relay-scheduled` (base `fix/scheduler-blind-spots` = PR #3, v2.2)
- **PR**: #4 — https://github.com/sbb2002/mewtype-scheduler/pull/4 (base `fix/scheduler-blind-spots`, 스택)
- 설계·계약: `docs/plan/v2_3_x_relay.md` (그림 `v2_3_x_relay.png`)
- 프론트 목업 아티팩트: https://claude.ai/code/artifact/92d6fa10-fb59-445a-9020-073891335941

---

## 1. 지금 상태 = "백엔드 인입 + reconcile + 프론트 카드" 완료, 실물 트윗 검증만 남음

### 구현 완료 (PR #4, 커밋 5개)

| 영역 | 내용 |
|------|------|
| `src/backend/xrelay.py` (신규) | `normalize` + `parse_bdp_schedule`(@BDP_yumemita 일일 스케줄, 실측 4샘플 self-test) + `merge_scheduled`(replace-by-date) + `summary_text`(계약 G). 아이콘→kind, `【メン限】`, `A×B` 콜라보, `／☀明日朝`→다음날, `頃`→approx, 연말 연도추론. 회원전용 `expires_at`=start+5h(공개 3h) |
| `src/backend/telegram_app.py` | `POST /ingest` — `X-Ingest-Secret` 헤더 인증, `paused` no-op, read-merge-write `schedule.json`(base-sha+1회 재시도), 결과 DM. `INGEST_DRY_RUN=1` → 저장 안 하고 받은 원문(`len`,앞3500자)+파싱결과 DM 회신 |
| `src/collector/reconcile.py` | `build_schedule` 이 `scheduled` 행 보존 — 같은 채널 실물 `upcoming`/`live` 가 ±4h 안이면 제거(supersede), `expires_at` 도달 시 제거, `scheduled_start` 지나면 `assumed_live=true`. 정렬 `live→upcoming→scheduled`, `_stable_view`/`sort_key` 를 video_id 없는 행에 안전하게 |
| `src/backend/handlers.py` | `_scheduled_wake_times` → `scheduled_start`(지금~+3h)마다 `light /tick` 1개 Cloud Tasks 예약(분버킷 dedupe). 공개 방송 정시 시작을 3h light 주기 안 기다리고 RSS 로 줍기 위함 |
| `src/frontend/js/render.js` | `scheduled` 행을 `upcoming` 과 같은 버킷에 `scheduled_start` 순으로. `KIND_LABEL`(게임/잡담/노래/합방/아침, unknown 생략). `updateCountdowns` 가 `.card--scheduled` 도 갱신하되 `late` 토글·`.card--sched-live` 는 스킵 |
| `src/frontend/css/{card,layout}.css` | `.card--scheduled`(점선·`opacity .82`, `card__icon`/없으면 📺, slate `card__badge--sched` "예고", `card__chip` 🔒, `card__approx` "약"), `.card--sched-live`(실선·빨강기 테두리, rel "방송 중 (추정)" 빨강). `--color-sched: #7c8aa0` |
| `deploy/` | `setup.sh`·`deploy_telegram.sh` — `INGEST_SECRET` 시크릿, `INGEST_DRY_RUN` env. `README.md` DRY-RUN·Automate 절차 |
| `docs/` | `plan/v2_3_x_relay.md`(+`gen_x_relay.py`/`.png`), `IMPLEMENTATION.md §1-1`(계약 A 확장)·`§3`(DOM), `CLAUDE.md` |

### self-test
```
python -m src.backend.xrelay
python -m src.collector.reconcile
python -m src.backend.handlers
node --check src/frontend/js/render.js
```

---

## 2. 지금 라이브로 떠 있는 것

- **`mewtype-telegram`** 최신 리비전에 `/ingest` 라이브, `INGEST_DRY_RUN=1`, `INGEST_SECRET` 시크릿 연결됨.
  - URL: `https://mewtype-telegram-376735243718.asia-northeast1.run.app` (`-lk3cg7l7ka-an.a.run.app` 도 같은 서비스)
  - 이 배포는 `deploy_telegram.sh --source .` = **브랜치 코드 기준**. main 아직 아님.
- **프론트는 미배포** (Vercel = main). `scheduled` 카드 코드는 브랜치에만.
- **폰 Automate (S23) 구성 완료**:
  ```
  Flow beginning
    → Notification posted?   package="com.sec.android.app.sbrowser"
                             out: pkg, ntitle, nmsg, nticker, nx(=dictionary of extras)
    → Expression true?       matches(coalesce(nx["android.bigText"], nx["android.text"],
                                              nmsg, nticker), "(?s).*配信スケジュール.*")
    → HTTP request           POST <telegram>/ingest
                             content-type: application/x-www-form-urlencoded
                             headers(dict, 이 빌드는 {} 표기): {"X-Ingest-Secret": "<INGEST_SECRET>"}
                             body: urlEncode({"text": coalesce(nx["android.bigText"],
                                     nx["android.text"], nmsg, nticker, "")})
                                   ── 커밋 1c21d9a 기준. 현행 상세는 v2_4_golive.md
    → (루프백) Notification posted?
  ```
  - **이 빌드 특성** (2026-09-04 확정): `||` 는 빈값만 뱉음 → `coalesce` 사용.
    `urlEncode({"text": expr})` 가 값을 키 자리로 흘림 → 전송 body 는 `<본문>=` 꼴.
    백엔드(`telegram_app.py` `_ingest`, `# ponytail:`)가 폼 키에서 원문 복구. 부계정 트윗으로 관통 확인.
  - **아직 안 됨**: 실물 `配信スケジュール` 트윗 왕복 (잘림 여부 확인 → `INGEST_ECHO=0,INGEST_DRY_RUN=0`).

---

## 3. 여기서부터 이어가기 (우선순위)

### 3-1. 실물 트윗 검증 → dry-run 해제  ★ 다음 할 일

실물 `@BDP_yumemita` `配信スケジュール` 트윗이 오면 DRY-RUN DM 에서 확인:
- `len(text)` + 원문에 **엔트리 전부 + 끝 `※時刻は予告なく…`** 다 왔나? (푸시 잘림 = 미해결 #1)
- 다 왔으면:
  ```
  gcloud run services update mewtype-telegram --region asia-northeast1 --update-env-vars INGEST_DRY_RUN=0
  ```
  → 이후 `/ingest` 가 `schedule.json` 에 실제 반영.
- **잘렸으면**: `xrelay.merge_scheduled` 에 "새 엔트리 수 < 그 날짜 기존 수 → replace 대신 upsert" 가드 추가.
  (`xrelay.py` `merge_scheduled` 상단에 `# ponytail:` 로 위치 표시해둠.)

### 3-2. 파서 B — 멤버 개인 트윗

`@BDP_yumemita` 외 5개 멤버 계정. 서식 제각각(`⋱配信予定⋰` / `【今日の配信】` / 자유문).
- 트리거: 본문에 `配信予定|配信告知|今日の配信|本日.*配信|はじまりました|生配信` AND 파서 A 미매치.
- 채널: `/update` 또는 `/ingest` body 의 `src=<X핸들>` (알림 제목이 텔레그램 경유로 유실 대비). Automate body 에 `&src=` 추가 필요.
- URL 에 온전한 `youtube.com/(watch\?v=|live/)([\w-]{11})` → **`videos.list` enrich** → 매칭되는 `scheduled` 행(같은 `channel_key`, `scheduled_start` ±4h)을 실물 `upcoming`/`live` 행으로 교체(썸네일·제목·URL 채움) → 기존 pending/wake 파이프라인 진입. 없으면 단일 `scheduled` 행(`source="member_tweet"`).
- Automate: `Expression true?` regex 확장하거나 별도 매크로 + `&src=` 파라미터.

### 3-3. 회원전용 → 실제 `live` 승격 (실험 필요)

**확인됨**: `search.list?eventType=live` 는 회원전용 미포함(OAuth 무관). `videos.list` 는 ID 만 있으면 회원전용도 메타 반환(키만으로). `members` API 는 크리에이터 전용·멤버명단용.

**미확인 (실제 회원전용 방송으로 테스트)**: `playlistItems.list(playlistId="UU"+channelId, part=snippet,contentDetails, maxResults=5)` 에 회원전용 upcoming/live 방송의 videoId 가 뜨나?
- 뜨면 → `handlers` 의 scheduled-wake tick 에서 해당 채널 uploads playlist 조회 → 최근 항목 videoId → `videos.list` `liveBroadcastContent` → 승격. 1 유닛/콜.
- 안 뜨면 → 파서 B(3-2)의 멤버 트윗 URL 만이 유일 경로.

### 3-4. 머지·배포

1. PR #3 (`fix/scheduler-blind-spots`) → main 머지.
2. PR #4 를 main 대상으로 rebase/재타깃 → 머지.
3. `bash deploy/deploy_telegram.sh` (main 기준 재배포). `INGEST_DRY_RUN` 은 검증 결과대로.
4. 프론트는 Vercel 자동배포.

### 3-5. 자잘한 것

- **아이콘 매핑 보강**: 현재 5종(🎮💭🎤💪☀). 새 이모지 발견 시 `xrelay.ICON_KIND` + `render.js KIND_LABEL` 만 수정. 미지 이모지는 `kind=unknown`+아이콘노출로 안전.
- 프론트 `scheduled` 카드 로컬 확인: `fixtures/schedule.sample.json` 복사 → scheduled 행 추가(`assumed_live` true/false 섞어) → `config.js` `DATA_URL` 을 그 파일로 → `python -m http.server 8099` → `localhost:8099/src/frontend/` → 확인 후 `config.js` 원복.

---

## 4. 열린 결정 (docs/plan/v2_3_x_relay.md §12)

- Automate 헤더 딕셔너리: 이 빌드는 `{}` 통함, `[]` 저장 거부.
- 파서 A `truncated` 필드/부분 upsert 가드: 미구현 (3-1 결과 보고).
- `/ingest` 시 `/tick` kick: 안 함 (다음 light tick 이 reconcile). scheduled-wake tick 이 사실상 그 역할.
